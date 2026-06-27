"""Per-provider LLM HTTP concurrency with configurable queue policy."""

from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, AsyncIterator

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PARALLEL = 1
_WAIT_POLL_SEC = 2.0
_cache_lock = threading.Lock()
_llm_wait_notifier: contextvars.ContextVar[Callable[[dict[str, Any]], None] | None] = (
    contextvars.ContextVar("llm_wait_notifier", default=None)
)
_last_wait_notify_floor: dict[str, int] = {}
_last_wait_notify_lock = threading.Lock()


def bind_llm_wait_notifier(
    notifier: Callable[[dict[str, Any]], None] | None,
) -> contextvars.Token:
    """Register a callback for ``agent.llm_slot_wait`` while the current context waits on a slot."""
    return _llm_wait_notifier.set(notifier)


def reset_llm_wait_notifier(token: contextvars.Token) -> None:
    _llm_wait_notifier.reset(token)


def _clamp_max_parallel(value: int | None) -> int:
    try:
        n = int(value if value is not None else _DEFAULT_MAX_PARALLEL)
    except (TypeError, ValueError):
        n = _DEFAULT_MAX_PARALLEL
    return max(1, min(64, n))


def max_parallel_for_provider(provider_id: str | None) -> int:
    from apps.backend.infrastructure.platform.config import config

    pid = (provider_id or "").strip()
    if not pid:
        return _clamp_max_parallel(getattr(config, "LLM_HTTP_MAX_PARALLEL_DEFAULT", 4))
    try:
        from apps.backend.infrastructure.providers.model_catalog_providers import get_provider_spec

        spec = get_provider_spec(pid)
        if spec is not None:
            return _clamp_max_parallel(spec.max_parallel)
    except Exception:
        logger.debug("max_parallel lookup failed for %r", pid, exc_info=True)
    return _DEFAULT_MAX_PARALLEL


@dataclass
class _Waiter:
    waiter_id: str
    priority: int
    enqueued_at: float
    user_key: str
    queue_class: str
    event: threading.Event = field(default_factory=threading.Event)


class _ProviderGate:
    def __init__(self, max_parallel: int) -> None:
        self.max_parallel = _clamp_max_parallel(max_parallel)
        self.active = 0
        self.waiters: list[_Waiter] = []
        self.lock = threading.Lock()
        self.rr_last_user_key: str | None = None

    def _ordered_waiters(self) -> list[_Waiter]:
        from apps.backend.infrastructure.agent_runtime.llm_queue_policy import load_queue_config

        cfg = load_queue_config()
        waiting = list(self.waiters)
        if not waiting:
            return []
        if cfg.policy == "fifo":
            return sorted(waiting, key=lambda w: w.enqueued_at)
        if cfg.policy == "round_robin":
            return self._round_robin_order(waiting)
        # priority (default): highest priority tier first; round-robin among peers in each tier
        by_prio: dict[int, list[_Waiter]] = defaultdict(list)
        for w in waiting:
            by_prio[w.priority].append(w)
        ordered: list[_Waiter] = []
        for prio in sorted(by_prio.keys(), reverse=True):
            ordered.extend(self._round_robin_order(by_prio[prio]))
        return ordered

    def _round_robin_order(self, waiters: list[_Waiter]) -> list[_Waiter]:
        if not waiters:
            return []
        groups: dict[str, list[_Waiter]] = defaultdict(list)
        for w in waiters:
            groups[w.user_key].append(w)
        for items in groups.values():
            items.sort(key=lambda x: x.enqueued_at)
        keys = sorted(groups.keys())
        if self.rr_last_user_key and self.rr_last_user_key in groups:
            idx = keys.index(self.rr_last_user_key)
            key_order = keys[idx + 1 :] + keys[: idx + 1]
        else:
            key_order = keys
        out: list[_Waiter] = []
        seen: set[str] = set()
        for uk in key_order:
            out.append(groups[uk][0])
            seen.add(uk)
        for uk in keys:
            if uk not in seen:
                out.append(groups[uk][0])
        return out

    def _queue_index(self, waiter: _Waiter) -> int:
        ordered = self._ordered_waiters()
        for i, w in enumerate(ordered):
            if w.waiter_id == waiter.waiter_id:
                return i
        return max(0, len(ordered) - 1)

    def try_acquire(self) -> bool:
        with self.lock:
            if self.active < self.max_parallel:
                self.active += 1
                return True
            return False

    def enqueue_and_wait(
        self,
        meta: Any,
        *,
        provider_key: str,
        max_parallel: int,
        notify: Callable[..., None],
    ) -> None:
        waiter = _Waiter(
            waiter_id=uuid.uuid4().hex,
            priority=meta.priority,
            enqueued_at=time.monotonic(),
            user_key=meta.user_key,
            queue_class=meta.queue_class,
        )
        with self.lock:
            if self.active < self.max_parallel:
                self.active += 1
                return
            self.waiters.append(waiter)

        started = time.monotonic()
        try:
            while True:
                with self.lock:
                    ahead = self._queue_index(waiter)
                    size = len(self.waiters)
                notify(
                    provider_key,
                    time.monotonic() - started,
                    max_parallel,
                    waiter_id=waiter.waiter_id,
                    queue_ahead=ahead,
                    queue_size=size,
                    queue_class=waiter.queue_class,
                    queue_priority=waiter.priority,
                )
                if waiter.event.wait(timeout=_WAIT_POLL_SEC):
                    return
        finally:
            with self.lock:
                self.waiters = [w for w in self.waiters if w.waiter_id != waiter.waiter_id]

    def release(self) -> None:
        with self.lock:
            self.active = max(0, self.active - 1)
            ordered = self._ordered_waiters()
            if not ordered or self.active >= self.max_parallel:
                return
            nxt = ordered[0]
            self.waiters = [w for w in self.waiters if w.waiter_id != nxt.waiter_id]
            self.active += 1
            self.rr_last_user_key = nxt.user_key
            nxt.event.set()


_gate_cache: dict[tuple[str, int], _ProviderGate] = {}


def _gate_for(provider_key: str, max_parallel: int) -> _ProviderGate:
    key = (provider_key, _clamp_max_parallel(max_parallel))
    with _cache_lock:
        gate = _gate_cache.get(key)
        if gate is None or gate.max_parallel != key[1]:
            gate = _ProviderGate(key[1])
            _gate_cache[key] = gate
        return gate


def invalidate_llm_concurrency_cache() -> None:
    with _cache_lock:
        _gate_cache.clear()
    with _last_wait_notify_lock:
        _last_wait_notify_floor.clear()


def _notify_slot_wait(
    provider_key: str,
    waited_sec: float,
    max_parallel: int,
    *,
    waiter_id: str | None = None,
    queue_ahead: int | None = None,
    queue_size: int | None = None,
    queue_class: str | None = None,
    queue_priority: int | None = None,
) -> None:
    cb = _llm_wait_notifier.get()
    if cb is None:
        return
    floor = int(waited_sec)
    with _last_wait_notify_lock:
        prev = _last_wait_notify_floor.get(provider_key, -1)
        if floor > 0 and floor <= prev:
            return
        _last_wait_notify_floor[provider_key] = floor
    try:
        payload: dict[str, Any] = {
            "type": "agent.llm_slot_wait",
            "provider_id": provider_key if provider_key != "__default__" else None,
            "waited_sec": round(max(0.0, waited_sec), 1),
            "max_parallel": max_parallel,
            "queue_ahead": max(0, int(queue_ahead or 0)),
            "queue_size": max(0, int(queue_size or 0)),
        }
        if queue_class:
            payload["queue_class"] = queue_class
        if queue_priority is not None:
            payload["queue_priority"] = queue_priority
        cb(payload)
    except Exception:
        logger.debug("llm slot wait notifier failed", exc_info=True)


def _acquire_with_policy(provider_key: str, max_parallel: int) -> None:
    from apps.backend.infrastructure.agent_runtime.llm_queue_policy import resolve_waiter_meta

    meta = resolve_waiter_meta()
    gate = _gate_for(provider_key, max_parallel)
    if gate.try_acquire():
        return
    _notify_slot_wait(provider_key, 0.0, max_parallel, queue_class=meta.queue_class, queue_priority=meta.priority)
    gate.enqueue_and_wait(
        meta,
        provider_key=provider_key,
        max_parallel=max_parallel,
        notify=_notify_slot_wait,
    )


def acquire_llm_slot(provider_id: str | None) -> str:
    """Block until a slot is available. Returns normalized provider key for release."""
    pid = (provider_id or "").strip() or "__default__"
    n = max_parallel_for_provider(provider_id)
    _acquire_with_policy(pid, n)
    return pid


def release_llm_slot(provider_key: str) -> None:
    pid = (provider_key or "").strip() or "__default__"
    n = max_parallel_for_provider(pid if pid != "__default__" else None)
    gate = _gate_for(pid, n)
    gate.release()


@contextmanager
def llm_slot(provider_id: str | None):
    key = acquire_llm_slot(provider_id)
    try:
        yield
    finally:
        release_llm_slot(key)


@asynccontextmanager
async def llm_slot_async(provider_id: str | None) -> AsyncIterator[None]:
    import asyncio

    pid = (provider_id or "").strip() or "__default__"
    n = max_parallel_for_provider(provider_id)
    await asyncio.to_thread(_acquire_with_policy, pid, n)
    try:
        yield
    finally:
        await asyncio.to_thread(release_llm_slot, pid)
