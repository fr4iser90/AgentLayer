"""GET /api/v1/scans/{id}/status — one-shot status check."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.integrations.simple_sec_check.ssc_common import (
    NO_WAIT_SUFFIX,
    agent_guidance_for_status,
    dump_ok,
    request,
    ssc_domain_attrs,
    ssc_status,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_status"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: status"
TOOL_DESCRIPTION = "One-shot SimpleSecCheck scan status (no waiting)."
TOOL_TRIGGERS = ("scan status", "simplesec status", "ssc status")


def security_scan_status(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    scan_id = str(arguments.get("scan_id") or arguments.get("id") or "").strip()
    if not scan_id:
        return dump_ok({"ok": False, "error": "scan_id is required"})
    status_code, data = request("GET", f"/api/v1/scans/{scan_id}/status")
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)
    st = ssc_status(data if isinstance(data, dict) else None)
    if st is None and isinstance(data, dict):
        st = str(data.get("scan_status") or "").strip().lower() or None
    terminal = st in ("completed", "failed", "cancelled", "error")
    still_running = st in ("started", "scanning", "queued", "running", "pending")
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "scan_id": scan_id,
            "status": st,
            "terminal": terminal,
            "still_running": still_running,
            "end_run_recommended": still_running,
            "progress": data.get("progress") if isinstance(data, dict) else None,
            "vulnerabilities_found": (
                data.get("vulnerabilities_found") if isinstance(data, dict) else None
            ),
            "scan": data,
            "agent_guidance": agent_guidance_for_status(st),
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_status": security_scan_status,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_status",
            "TOOL_DESCRIPTION": (
                "One-shot scan status check (progress, completed, failed). "
                "If still running, end the run and check again in a later session."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_id": {"type": "string", "TOOL_DESCRIPTION": "Scan UUID"},
                },
                "required": ["scan_id"],
            },
        },
    },
]
