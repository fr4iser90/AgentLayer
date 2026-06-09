"""Per-provider LLM HTTP concurrency (replaces process-wide serialize lock)."""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, AsyncIterator

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PARALLEL = 1
_WAIT_POLL_SEC = 2.0
_semaphore_cache: dict[str, tuple[int, threading.BoundedSemaphore]] = {}
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
    from apps.backend.core.config import config

    pid = (provider_id or "").strip()
    if not pid:
        return _clamp_max_parallel(getattr(config, "LLM_HTTP_MAX_PARALLEL_DEFAULT", 4))
    try:
        from apps.backend.infrastructure.model_catalog_providers import get_provider_spec

        spec = get_provider_spec(pid)
        if spec is not None:
            return _clamp_max_parallel(spec.max_parallel)
    except Exception:
        logger.debug("max_parallel lookup failed for %r", pid, exc_info=True)
    return _DEFAULT_MAX_PARALLEL


def _semaphore_for(provider_id: str, max_parallel: int) -> threading.BoundedSemaphore:
    key = (provider_id or "__default__").strip() or "__default__"
    n = _clamp_max_parallel(max_parallel)
    with _cache_lock:
        prev = _semaphore_cache.get(key)
        if prev is not None and prev[0] == n:
            return prev[1]
        sem = threading.BoundedSemaphore(n)
        _semaphore_cache[key] = (n, sem)
        return sem


def invalidate_llm_concurrency_cache() -> None:
    with _cache_lock:
        _semaphore_cache.clear()
    with _last_wait_notify_lock:
        _last_wait_notify_floor.clear()


def _notify_slot_wait(provider_key: str, waited_sec: float, max_parallel: int) -> None:
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
        cb(
            {
                "type": "agent.llm_slot_wait",
                "provider_id": provider_key if provider_key != "__default__" else None,
                "waited_sec": round(max(0.0, waited_sec), 1),
                "max_parallel": max_parallel,
            }
        )
    except Exception:
        logger.debug("llm slot wait notifier failed", exc_info=True)


def _acquire_semaphore_with_wait(
    sem: threading.BoundedSemaphore,
    provider_key: str,
    max_parallel: int,
) -> None:
    if sem.acquire(blocking=False):
        return
    started = time.monotonic()
    _notify_slot_wait(provider_key, 0.0, max_parallel)
    while True:
        if sem.acquire(timeout=_WAIT_POLL_SEC):
            return
        _notify_slot_wait(provider_key, time.monotonic() - started, max_parallel)


def acquire_llm_slot(provider_id: str | None) -> str:
    """Block until a slot is available. Returns normalized provider key for release."""
    pid = (provider_id or "").strip() or "__default__"
    n = max_parallel_for_provider(provider_id)
    sem = _semaphore_for(pid, n)
    _acquire_semaphore_with_wait(sem, pid, n)
    return pid


def release_llm_slot(provider_key: str) -> None:
    with _cache_lock:
        entry = _semaphore_cache.get(provider_key)
    if entry is None:
        return
    try:
        entry[1].release()
    except ValueError:
        logger.warning("llm concurrency: release on unheld slot provider=%s", provider_key)


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
    sem = _semaphore_for(pid, n)
    if not await asyncio.to_thread(sem.acquire, False):
        started = time.monotonic()
        _notify_slot_wait(pid, 0.0, n)
        while True:
            got = await asyncio.to_thread(sem.acquire, True, _WAIT_POLL_SEC)
            if got:
                break
            _notify_slot_wait(pid, time.monotonic() - started, n)
    try:
        yield
    finally:
        release_llm_slot(pid)
