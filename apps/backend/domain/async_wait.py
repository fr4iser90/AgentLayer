"""Generic interruptible deferred wait (estimate-aware poll loop)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DEFAULT_POLL_SEC = 15.0
_SLEEP_CHUNK_SEC = 5.0
_ESTIMATE_BUFFER_SEC = 300
_MAX_WAIT_WITHOUT_ESTIMATE_SEC = 3600.0


def parse_estimated_time_seconds(data: dict[str, Any] | None) -> int | None:
    if not isinstance(data, dict):
        return None
    raw = data.get("estimated_time_seconds")
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _cancel_checker(context: dict[str, Any] | None) -> Callable[[], bool]:
    def _is_cancelled() -> bool:
        if not context:
            return False
        ce = context.get("cancel_event")
        if ce is not None and hasattr(ce, "is_set") and ce.is_set():
            return True
        run_id = context.get("agent_run_id")
        if isinstance(run_id, str) and run_id.strip():
            try:
                from apps.backend.domain.agent_run_cancel import parent_cancel_event

                evt = parent_cancel_event(run_id.strip())
                if evt is not None and evt.is_set():
                    return True
            except Exception:
                logger.debug("deferred wait cancel lookup failed", exc_info=True)
        return False

    return _is_cancelled


def _deferred_wait_notify(context: dict[str, Any] | None, payload: dict[str, Any]) -> None:
    cb = None
    if context:
        cb = (
            context.get("deferred_wait_notify")
            or context.get("scan_wait_notify")
            or context.get("agent_subagent_notify")
        )
    if cb is None:
        return
    ev = dict(payload)
    ev.setdefault("type", "agent.deferred_wait")
    try:
        cb(ev)
    except Exception:
        logger.debug("deferred wait notify failed", exc_info=True)


def run_deferred_wait(
    *,
    wait_id: str | None,
    estimated_sec: int | None,
    context: dict[str, Any] | None = None,
    initial_status: str | None = None,
    poll_fn: Callable[[], tuple[dict[str, Any] | None, str | None]],
    terminal_ok: frozenset[str],
    terminal_fail: frozenset[str],
    poll_interval_sec: float = _DEFAULT_POLL_SEC,
    wait_label: str | None = None,
) -> dict[str, Any]:
    """Poll until terminal status, estimate elapsed, or timeout. Does not hold LLM slots."""
    wid = str(wait_id or "").strip() or None
    cancelled = _cancel_checker(context)
    if cancelled():
        return {
            "ok": False,
            "cancelled": True,
            "wait_id": wid,
            "waited_sec": 0.0,
        }

    if estimated_sec is not None:
        max_wait = float(estimated_sec + _ESTIMATE_BUFFER_SEC)
    else:
        max_wait = _MAX_WAIT_WITHOUT_ESTIMATE_SEC

    waited = 0.0
    poll_count = 0
    last_status = (initial_status or "").strip().lower() or None
    last_data: dict[str, Any] | None = None

    _deferred_wait_notify(
        context,
        {
            "phase": "started",
            "wait_id": wid,
            "wait_label": wait_label,
            "status": last_status,
            "estimated_time_seconds": estimated_sec,
        },
    )

    try:
        deadline = time.monotonic() + max_wait
        next_poll_at = time.monotonic()

        while time.monotonic() < deadline:
            if cancelled():
                return {
                    "ok": False,
                    "cancelled": True,
                    "wait_id": wid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                }

            est_remaining: int | None = None
            if estimated_sec is not None:
                est_remaining = max(0, int(estimated_sec) - int(waited))

            _deferred_wait_notify(
                context,
                {
                    "phase": "waiting",
                    "wait_id": wid,
                    "wait_label": wait_label,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "estimated_time_seconds": estimated_sec,
                    "estimated_remaining_sec": est_remaining,
                },
            )

            remaining = max(0.0, deadline - time.monotonic())
            chunk = min(_SLEEP_CHUNK_SEC, poll_interval_sec, remaining)
            if chunk > 0:
                time.sleep(chunk)
                waited += chunk

            if time.monotonic() < next_poll_at:
                continue

            poll_count += 1
            next_poll_at = time.monotonic() + poll_interval_sec
            data, st = poll_fn()
            if isinstance(data, dict) and data.get("ok") is False:
                return {
                    "ok": False,
                    "wait_id": wid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "error": data.get("error") or "poll failed",
                    "poll_result": data,
                }
            if st:
                last_status = st.strip().lower()
            if data is not None:
                last_data = data
            if last_status in terminal_ok:
                return {
                    "ok": True,
                    "wait_id": wid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "poll_result": last_data,
                    "completed": True,
                }
            if last_status in terminal_fail:
                return {
                    "ok": False,
                    "wait_id": wid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "poll_result": last_data,
                    "completed": True,
                }

        data, st = poll_fn()
        if st:
            last_status = st.strip().lower()
        if isinstance(data, dict):
            last_data = data
        timed_out = last_status not in terminal_ok and last_status not in terminal_fail
        return {
            "ok": last_status in terminal_ok,
            "wait_id": wid,
            "status": last_status,
            "waited_sec": round(waited, 1),
            "poll_count": poll_count,
            "poll_result": last_data,
            "timed_out": timed_out,
            "completed": not timed_out,
        }
    finally:
        _deferred_wait_notify(
            context,
            {
                "phase": "ended",
                "wait_id": wid,
                "wait_label": wait_label,
                "status": last_status,
                "waited_sec": round(waited, 1),
                "estimated_time_seconds": estimated_sec,
            },
        )
