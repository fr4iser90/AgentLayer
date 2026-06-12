"""Security scan integration with platform deferred_wait tool."""

from __future__ import annotations

import json
from typing import Any

from apps.backend.domain.async_wait import parse_estimated_time_seconds
from apps.backend.domain.security_scan.common import bool_arg, normalize_findings

_IN_PROGRESS = frozenset({"started", "scanning", "queued", "running", "pending"})
_TERMINAL_OK = frozenset({"ready", "completed"})
_TERMINAL_FAIL = frozenset({"failed", "cancelled", "error"})


def is_scan_in_progress(st: str | None) -> bool:
    return (st or "").strip().lower() in _IN_PROGRESS


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
    if bool_arg(arguments, "skip_scan_wait", False) or bool_arg(arguments, "skip_wait", False):
        return False
    if bool_arg(arguments, "wait_for_completion", False):
        return True
    if estimated_sec is not None:
        return True
    if context and context.get("benchmark_run_id"):
        return True
    return False


def invoke_scan_deferred_wait(
    scan_id: str,
    *,
    estimated_sec: int | None,
    context: dict[str, Any] | None,
    initial_status: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from apps.backend.domain.plugin_system.tools import run_tool

    wait_args: dict[str, Any] = {
        "wait_id": scan_id,
        "estimated_time_seconds": estimated_sec,
        "poll_tool": "status",
        "poll_arguments": {"scan_id": scan_id},
        "terminal_statuses": sorted(_TERMINAL_OK | _TERMINAL_FAIL),
        "status_field": "status",
        "initial_status": initial_status,
        "wait_label": "security_scan",
    }
    if bool_arg(arguments, "skip_scan_wait", False):
        wait_args["skip_wait"] = True

    raw = run_tool("deferred_wait", wait_args, context)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "deferred_wait returned invalid JSON", "raw": raw}


def merge_wait_into_payload(
    payload: dict[str, Any],
    *,
    wait_result: dict[str, Any],
    api_data: dict[str, Any] | None,
) -> None:
    payload["deferred_wait"] = {
        "waited_sec": wait_result.get("waited_sec"),
        "poll_count": wait_result.get("poll_count"),
        "cancelled": bool(wait_result.get("cancelled")),
        "timed_out": bool(wait_result.get("timed_out")),
        "skipped": bool(wait_result.get("skipped")),
    }
    if wait_result.get("skipped"):
        return
    if wait_result.get("cancelled"):
        payload["ok"] = False
        payload["error"] = "Scan wait cancelled"
        payload["defer"] = False
        payload["end_run_recommended"] = True
        return

    st = wait_result.get("status")
    if isinstance(st, str) and st.strip():
        payload["status"] = st.strip().lower()

    poll_result = wait_result.get("poll_result")
    scan_data: dict[str, Any] | None = None
    if isinstance(poll_result, dict):
        nested = poll_result.get("scan")
        scan_data = nested if isinstance(nested, dict) else poll_result
        payload["progress"] = poll_result.get("progress") or payload.get("progress")
        payload["summary"] = poll_result.get("summary") or payload.get("summary")
        est = parse_estimated_time_seconds(poll_result) or parse_estimated_time_seconds(scan_data)
        if est is not None:
            payload["estimated_time_seconds"] = est

    if payload.get("status") == "ready":
        findings = normalize_findings(api_data or scan_data)
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
