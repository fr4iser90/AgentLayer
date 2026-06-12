"""Interruptible SimpleSecCheck scan wait (estimate-aware poll loop)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    bool_arg,
    normalize_findings,
    request,
    ssc_status,
)

logger = logging.getLogger(__name__)

_IN_PROGRESS = frozenset({"started", "scanning", "queued", "running", "pending"})
_TERMINAL_OK = frozenset({"ready", "completed"})
_TERMINAL_FAIL = frozenset({"failed", "cancelled", "error"})
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


def is_scan_in_progress(st: str | None) -> bool:
    return (st or "").strip().lower() in _IN_PROGRESS


def is_scan_terminal(st: str | None) -> bool:
    s = (st or "").strip().lower()
    return s in _TERMINAL_OK or s in _TERMINAL_FAIL


def should_wait_for_scan(
    arguments: dict[str, Any],
    context: dict[str, Any] | None,
    *,
    st: str | None,
    estimated_sec: int | None,
    scan_id: str | None,
) -> bool:
    if not scan_id or not is_scan_in_progress(st):
        return False
    if bool_arg(arguments, "wait_for_completion", False):
        return True
    if bool_arg(arguments, "skip_scan_wait", False):
        return False
    if estimated_sec is not None and context and context.get("benchmark_run_id"):
        return True
    return False


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
                logger.debug("scan wait cancel lookup failed", exc_info=True)
        return False

    return _is_cancelled


def _scan_wait_notify(context: dict[str, Any] | None, payload: dict[str, Any]) -> None:
    cb = None
    if context:
        cb = context.get("scan_wait_notify") or context.get("agent_subagent_notify")
    if cb is None:
        return
    ev = dict(payload)
    ev.setdefault("type", "agent.scan_wait")
    try:
        cb(ev)
    except Exception:
        logger.debug("scan wait notify failed", exc_info=True)


def fetch_scan_status(scan_id: str) -> tuple[int, dict[str, Any] | None, str | None]:
    status_code, data = request("GET", f"/api/v1/scans/{scan_id}/status")
    if isinstance(data, dict) and data.get("ok") is False:
        return status_code, data, None
    st = ssc_status(data if isinstance(data, dict) else None)
    if st is None and isinstance(data, dict):
        st = str(data.get("scan_status") or "").strip().lower() or None
    return status_code, data if isinstance(data, dict) else None, st


def wait_for_scan_completion(
    scan_id: str,
    *,
    estimated_sec: int | None,
    context: dict[str, Any] | None = None,
    initial_status: str | None = None,
    poll_interval_sec: float = _DEFAULT_POLL_SEC,
) -> dict[str, Any]:
    """Poll until scan terminal, estimate elapsed, or timeout. Does not hold LLM slots."""
    sid = str(scan_id or "").strip()
    if not sid:
        return {"ok": False, "error": "scan_id is required for wait", "cancelled": False}

    cancelled = _cancel_checker(context)
    if cancelled():
        return {"ok": False, "cancelled": True, "scan_id": sid, "waited_sec": 0.0}

    if estimated_sec is not None:
        max_wait = float(estimated_sec + _ESTIMATE_BUFFER_SEC)
    else:
        max_wait = _MAX_WAIT_WITHOUT_ESTIMATE_SEC

    waited = 0.0
    poll_count = 0
    last_status = (initial_status or "").strip().lower() or None
    last_data: dict[str, Any] | None = None

    _scan_wait_notify(
        context,
        {
            "phase": "started",
            "scan_id": sid,
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
                    "scan_id": sid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                }

            est_remaining: int | None = None
            if estimated_sec is not None:
                est_remaining = max(0, int(estimated_sec) - int(waited))

            _scan_wait_notify(
                context,
                {
                    "phase": "waiting",
                    "scan_id": sid,
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
            _http, data, st = fetch_scan_status(sid)
            if isinstance(data, dict) and data.get("ok") is False:
                return {
                    "ok": False,
                    "scan_id": sid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "error": data.get("error") or "status poll failed",
                    "response": data,
                }
            if st:
                last_status = st
            if data is not None:
                last_data = data
            if last_status in _TERMINAL_OK:
                return {
                    "ok": True,
                    "scan_id": sid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "scan": last_data,
                    "completed": True,
                }
            if last_status in _TERMINAL_FAIL:
                return {
                    "ok": False,
                    "scan_id": sid,
                    "status": last_status,
                    "waited_sec": round(waited, 1),
                    "poll_count": poll_count,
                    "scan": last_data,
                    "completed": True,
                }

        _http, data, st = fetch_scan_status(sid)
        if st:
            last_status = st
        if isinstance(data, dict):
            last_data = data
        timed_out = last_status not in _TERMINAL_OK and last_status not in _TERMINAL_FAIL
        return {
            "ok": last_status in _TERMINAL_OK,
            "scan_id": sid,
            "status": last_status,
            "waited_sec": round(waited, 1),
            "poll_count": poll_count,
            "scan": last_data,
            "timed_out": timed_out,
            "completed": not timed_out,
        }
    finally:
        _scan_wait_notify(
            context,
            {
                "phase": "ended",
                "scan_id": sid,
                "status": last_status,
                "waited_sec": round(waited, 1),
                "estimated_time_seconds": estimated_sec,
            },
        )


def merge_wait_into_payload(
    payload: dict[str, Any],
    *,
    wait_result: dict[str, Any],
    api_data: dict[str, Any] | None,
) -> None:
    payload["scan_wait"] = {
        "waited_sec": wait_result.get("waited_sec"),
        "poll_count": wait_result.get("poll_count"),
        "cancelled": bool(wait_result.get("cancelled")),
        "timed_out": bool(wait_result.get("timed_out")),
    }
    if wait_result.get("cancelled"):
        payload["ok"] = False
        payload["error"] = "Scan wait cancelled"
        payload["defer"] = False
        payload["end_run_recommended"] = True
        return

    st = wait_result.get("status")
    if isinstance(st, str) and st.strip():
        payload["status"] = st.strip().lower()
    scan = wait_result.get("scan")
    if isinstance(scan, dict):
        payload["progress"] = scan.get("progress") or payload.get("progress")
        payload["summary"] = scan.get("summary") or payload.get("summary")
        est = parse_estimated_time_seconds(scan)
        if est is not None:
            payload["estimated_time_seconds"] = est

    if payload.get("status") == "ready":
        findings = normalize_findings(api_data or wait_result.get("scan"))
        if findings:
            payload["findings"] = findings
        payload["defer"] = False
        payload["end_run_recommended"] = False
        payload["agent_guidance"] = [
            "Scan finished while waiting. Findings may be in this response; use security_scan_findings for more pages."
        ]
    elif payload.get("status") in _TERMINAL_FAIL:
        payload["defer"] = False
        payload["end_run_recommended"] = True
    elif wait_result.get("timed_out"):
        payload["defer"] = True
        payload["end_run_recommended"] = True
        payload.setdefault("agent_guidance", []).append(
            "Scan wait timed out before completion; check security_scan_status in a later run."
        )
