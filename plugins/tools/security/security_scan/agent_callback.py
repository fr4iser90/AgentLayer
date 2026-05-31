"""POST /api/user/targets/{id}/agent-callback — queue rescan after fix branch."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    END_RUN_GUIDANCE,
    NO_WAIT_SUFFIX,
    bool_arg,
    dump_ok,
    request,
    ssc_domain_attrs,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_callback"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: rescan"
TOOL_DESCRIPTION = "Notify SimpleSecCheck to rescan a fix branch."
TOOL_TRIGGERS = ("rescan", "agent callback", "ssc callback")


def agent_callback(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    target_id = str(arguments.get("target_id") or arguments.get("id") or "").strip()
    if not target_id:
        return dump_ok(
            {
                "ok": False,
                "error": "target_id is required (from security_scan_resolve or security_scan_targets_list)",
            }
        )
    branch_name = str(arguments.get("branch_name") or arguments.get("branch") or "").strip()
    if not branch_name:
        return dump_ok({"ok": False, "error": "branch_name is required"})

    body: dict[str, Any] = {
        "branch_name": branch_name,
        "trigger_rescan": bool_arg(arguments, "trigger_rescan", True),
        "agent_name": str(arguments.get("agent_name") or "agentlayer").strip(),
    }
    for opt in ("pr_url", "commit_sha"):
        v = arguments.get(opt)
        if v is not None and str(v).strip():
            body[opt] = str(v).strip()
    meta = arguments.get("metadata")
    if isinstance(meta, dict):
        body["metadata"] = meta

    status_code, data = request(
        "POST",
        f"/api/user/targets/{target_id}/agent-callback",
        json_body=body,
        timeout=60.0,
    )
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)

    new_scan_id = data.get("scan_id") if isinstance(data, dict) else None
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "target_id": target_id,
            "branch_name": branch_name,
            "scan_id": new_scan_id,
            "response": data,
            "defer": True,
            "end_run_recommended": True,
            "agent_guidance": [
                "Rescan queued. " + END_RUN_GUIDANCE,
                "Later: security_scan_status(scan_id) once in a new session, then security_scan_findings.",
            ],
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "agent_callback": agent_callback,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "agent_callback",
            "TOOL_DESCRIPTION": (
                "After pushing a fix branch, notify SSC to rescan. Returns new scan_id; end the run."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "My Targets id from resolve or targets_list",
                    },
                    "branch_name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Feature branch that was pushed",
                    },
                    "trigger_rescan": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Queue rescan (default true)",
                    },
                    "pr_url": {"type": "string", "TOOL_DESCRIPTION": "Optional PR URL"},
                    "commit_sha": {"type": "string", "TOOL_DESCRIPTION": "Optional commit on branch"},
                    "metadata": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Optional metadata dict for SSC",
                    },
                },
                "required": ["target_id", "branch_name"],
            },
        },
    },
]
