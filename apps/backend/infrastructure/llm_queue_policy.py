"""LLM slot queue policy (priority / FIFO / round-robin) — operator + per-user settings."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

VALID_POLICIES = frozenset({"fifo", "priority", "round_robin"})
_DEFAULT_USER_PRIORITY = 100
_DEFAULT_BENCHMARK_PRIORITY = 10
_DEFAULT_SCHEDULER_PRIORITY = 50

_user_priority_cache: dict[str, tuple[float, int | None]] = {}
_USER_PRIORITY_CACHE_TTL_SEC = 60.0


@dataclass(frozen=True)
class QueueConfig:
    policy: str
    user_priority: int
    benchmark_priority: int
    scheduler_priority: int


@dataclass(frozen=True)
class WaiterMeta:
    priority: int
    user_key: str
    queue_class: str


def _clamp_priority(value: Any, default: int) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(0, min(1000, n))


def load_queue_config() -> QueueConfig:
    from apps.backend.infrastructure.operator_settings import _cached_row

    r = _cached_row()
    policy = str(r.get("llm_queue_policy") or "priority").strip().lower()
    if policy not in VALID_POLICIES:
        policy = "priority"
    return QueueConfig(
        policy=policy,
        user_priority=_clamp_priority(r.get("llm_queue_user_priority"), _DEFAULT_USER_PRIORITY),
        benchmark_priority=_clamp_priority(
            r.get("llm_queue_benchmark_priority"), _DEFAULT_BENCHMARK_PRIORITY
        ),
        scheduler_priority=_clamp_priority(
            r.get("llm_queue_scheduler_priority"), _DEFAULT_SCHEDULER_PRIORITY
        ),
    )


def _user_priority_override(user_id: uuid.UUID) -> int | None:
    key = str(user_id)
    now = time.monotonic()
    cached = _user_priority_cache.get(key)
    if cached is not None and now - cached[0] < _USER_PRIORITY_CACHE_TTL_SEC:
        return cached[1]
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT llm_queue_priority FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
        raw = row[0] if row else None
        if raw is None:
            val: int | None = None
        else:
            val = _clamp_priority(raw, _DEFAULT_USER_PRIORITY)
    except Exception:
        logger.debug("user llm_queue_priority lookup failed", exc_info=True)
        val = None
    _user_priority_cache[key] = (now, val)
    return val


def invalidate_user_priority_cache(user_id: uuid.UUID | None = None) -> None:
    if user_id is None:
        _user_priority_cache.clear()
        return
    _user_priority_cache.pop(str(user_id), None)


def resolve_waiter_meta() -> WaiterMeta:
    from apps.backend.domain.identity import get_benchmark_run_id, get_identity, get_llm_queue_source

    _, uid = get_identity()
    bench = get_benchmark_run_id()
    source = (get_llm_queue_source() or "chat").strip().lower()
    cfg = load_queue_config()

    if bench is not None:
        queue_class = "benchmark"
        user_key = f"bench:{bench}"
        priority = cfg.benchmark_priority
    elif source == "scheduler":
        queue_class = "scheduler"
        user_key = f"sched:{uid or 'anon'}"
        priority = cfg.scheduler_priority
    else:
        queue_class = "user"
        user_key = str(uid) if uid is not None else "anon"
        priority = cfg.user_priority

    if uid is not None:
        override = _user_priority_override(uid)
        if override is not None:
            priority = override

    return WaiterMeta(priority=priority, user_key=user_key, queue_class=queue_class)
