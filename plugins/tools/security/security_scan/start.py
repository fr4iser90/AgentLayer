"""POST /api/v1/scans/ — low-level scan enqueue."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    END_RUN_GUIDANCE,
    NO_WAIT_SUFFIX,
    dump_ok,
    request,
    resolve_repo_url,
    ssc_domain_attrs,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_start"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = "security_scan"
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: start scan"
TOOL_DESCRIPTION = "Low-level scan enqueue (prefer security_scan_resolve)."
TOOL_TRIGGERS = ("start scan", "enqueue scan")


def start(arguments: dict[str, Any], context: dict | None = None) -> str:
    repo_url = resolve_repo_url(arguments, context)
    if not repo_url:
        return dump_ok(
            {
                "ok": False,
                "error": (
                    "repo_url is required (or bind a workspace with git_url / origin remote). "
                    'Example: {"repo_url": "https://github.com/org/repo.git", "branch": "main"}'
                ),
            }
        )
    body: dict[str, Any] = {"repo_url": repo_url}
    branch = str(arguments.get("branch") or arguments.get("ref") or "").strip()
    if branch:
        body["branch"] = branch
    for opt in ("scan_type", "name", "callback_url"):
        v = arguments.get(opt)
        if v is not None and str(v).strip():
            body[opt] = str(v).strip()
    status_code, data = request("POST", "/api/v1/scans/", json_body=body, timeout=60.0)
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)
    scan_id = data.get("id") or data.get("scan_id") if isinstance(data, dict) else None
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "scan_id": scan_id,
            "repo_url": repo_url,
            "branch": branch or None,
            "scan": data,
            "defer": True,
            "end_run_recommended": True,
            "agent_guidance": [END_RUN_GUIDANCE],
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "start": start,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "start",
            "TOOL_DESCRIPTION": (
                "Low-level scan enqueue (POST /api/v1/scans/). Prefer security_scan_resolve."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "TOOL_DESCRIPTION": "HTTPS Git clone URL"},
                    "branch": {"type": "string", "TOOL_DESCRIPTION": "Branch name"},
                    "scan_type": {"type": "string", "TOOL_DESCRIPTION": "Optional scan profile"},
                },
            },
        },
    },
]
