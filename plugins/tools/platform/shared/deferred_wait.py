"""Platform deferred wait — poll until async work completes (estimate-aware)."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.async_wait import parse_estimated_time_seconds, run_deferred_wait

__version__ = "1.0.0"
TOOL_ID = "deferred_wait"
TOOL_BUCKET = "network"
TOOL_RISK_LEVEL = 1
TOOL_LABEL = "Deferred wait"
TOOL_DESCRIPTION = (
    "Wait for deferred/async work when an API returns estimated_time_seconds. "
    "Polls another tool until terminal status."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_DOMAIN = "shared"
TOOL_TAGS = ("wait", "async", "poll", "shared")
TOOL_REQUIRES: list[str] = []
TOOL_CAPABILITIES = ("platform.deferred_wait",)

_TERMINAL_OK = frozenset({"ready", "completed", "done", "success"})
_TERMINAL_FAIL = frozenset({"failed", "cancelled", "error"})


def _extract_status(data: dict[str, Any] | None, status_field: str) -> str | None:
    if not isinstance(data, dict):
        return None
    raw = data.get(status_field)
    if raw is None and status_field == "status":
        nested = data.get("scan")
        if isinstance(nested, dict):
            raw = nested.get("status") or nested.get("scan_status")
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s or None


def deferred_wait(arguments: dict[str, Any], context: dict | None = None) -> str:
    if arguments.get("skip_wait") is True:
        return json.dumps({"ok": True, "skipped": True, "waited_sec": 0.0}, ensure_ascii=False)

    poll_tool = str(arguments.get("poll_tool") or "").strip()
    if not poll_tool:
        return json.dumps(
            {"ok": False, "error": "poll_tool is required for deferred_wait"},
            ensure_ascii=False,
        )

    poll_args = arguments.get("poll_arguments")
    if not isinstance(poll_args, dict):
        poll_args = {}

    status_field = str(arguments.get("status_field") or "status").strip() or "status"
    terminal_raw = arguments.get("terminal_statuses")
    if isinstance(terminal_raw, list) and terminal_raw:
        terminal_all = frozenset(str(x).strip().lower() for x in terminal_raw if str(x).strip())
    else:
        terminal_all = _TERMINAL_OK | _TERMINAL_FAIL

    terminal_ok = terminal_all & (_TERMINAL_OK | frozenset({"ready"}))
    terminal_fail = terminal_all & (_TERMINAL_FAIL | frozenset({"failed", "cancelled", "error"}))
    if not terminal_ok:
        terminal_ok = frozenset(x for x in terminal_all if x not in terminal_fail)
    if not terminal_fail:
        terminal_fail = frozenset(x for x in terminal_all if x not in terminal_ok)

    wait_id = str(arguments.get("wait_id") or "").strip() or None
    wait_label = str(arguments.get("wait_label") or "").strip() or None
    initial_status = str(arguments.get("initial_status") or "").strip().lower() or None
    estimated_sec = parse_estimated_time_seconds(arguments)
    if estimated_sec is None and isinstance(arguments.get("estimated_time_seconds"), (int, float)):
        try:
            n = int(arguments["estimated_time_seconds"])
            estimated_sec = n if n > 0 else None
        except (TypeError, ValueError):
            estimated_sec = None

    poll_interval = 15.0
    if arguments.get("poll_interval_sec") is not None:
        try:
            poll_interval = max(1.0, float(arguments["poll_interval_sec"]))
        except (TypeError, ValueError):
            poll_interval = 15.0

    from apps.backend.domain.plugin_system.tools import run_tool

    def poll_fn() -> tuple[dict[str, Any] | None, str | None]:
        raw = run_tool(poll_tool, dict(poll_args), context)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "poll tool returned invalid JSON", "raw": raw}, None
        st = _extract_status(data, status_field)
        if st and st in terminal_all:
            return data, st
        return data, st

    result = run_deferred_wait(
        wait_id=wait_id,
        estimated_sec=estimated_sec,
        context=context,
        initial_status=initial_status,
        poll_fn=poll_fn,
        terminal_ok=terminal_ok,
        terminal_fail=terminal_fail,
        poll_interval_sec=poll_interval,
        wait_label=wait_label,
    )
    return json.dumps(result, ensure_ascii=False)


HANDLERS: dict[str, Callable[..., str]] = {
    "deferred_wait": deferred_wait,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "deferred_wait",
            "TOOL_DESCRIPTION": (
                "Wait for async/deferred work when estimated_time_seconds is known. "
                "Polls poll_tool until status is terminal. Call after resolve/start when "
                "a scan is still running; repeat as needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "estimated_time_seconds": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Server estimate from async API response",
                    },
                    "poll_tool": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Registered tool name to call each poll interval",
                    },
                    "poll_arguments": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Arguments passed to poll_tool on each poll",
                    },
                    "terminal_statuses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "TOOL_DESCRIPTION": "Status values that end the wait (default ready/completed/failed/...)",
                    },
                    "status_field": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Field on poll JSON for status (default status)",
                    },
                    "wait_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional id for UI/events (e.g. scan_id)",
                    },
                    "wait_label": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional label for UI (e.g. security_scan)",
                    },
                    "initial_status": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Status before first poll",
                    },
                    "poll_interval_sec": {
                        "type": "number",
                        "TOOL_DESCRIPTION": "Seconds between poll_tool calls (default 15)",
                    },
                    "skip_wait": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Skip waiting and return immediately",
                    },
                },
                "required": ["poll_tool"],
            },
        },
    },
]
