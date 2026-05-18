"""POST /api/v1/resolve-scan — primary SimpleSecCheck entry."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.integrations.simple_sec_check.ssc_common import (
    DEFAULT_FINDINGS_LIMIT,
    MAX_FINDINGS_LIMIT,
    NO_WAIT_SUFFIX,
    agent_guidance_for_status,
    base_url,
    bool_arg,
    dump_ok,
    normalize_findings,
    request,
    resolve_repo_url,
    ssc_domain_attrs,
    ssc_status,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_resolve"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck"
TOOL_DESCRIPTION = (
    "Resolve or enqueue security scans on SimpleSecCheck (https://scan.fr4iser.com)."
)
TOOL_TRIGGERS = ("security scan", "resolve-scan", "simplesec", "ssc")


def security_scan_resolve(arguments: dict[str, Any], context: dict | None = None) -> str:
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
    body: dict[str, Any] = {
        "repo_url": repo_url,
        "check_commit": bool_arg(arguments, "check_commit", True),
        "force_scan": bool_arg(arguments, "force_scan", False),
    }
    branch = str(arguments.get("branch") or arguments.get("ref") or "").strip()
    if branch:
        body["branch"] = branch
    if arguments.get("findings_limit") is not None:
        body["findings_limit"] = min(
            max(int(arguments["findings_limit"]), 1), MAX_FINDINGS_LIMIT
        )
    elif arguments.get("limit") is not None:
        body["findings_limit"] = min(max(int(arguments["limit"]), 1), MAX_FINDINGS_LIMIT)
    else:
        body["findings_limit"] = DEFAULT_FINDINGS_LIMIT
    if arguments.get("findings_offset") is not None:
        body["findings_offset"] = max(int(arguments["findings_offset"]), 0)
    elif arguments.get("offset") is not None:
        body["findings_offset"] = max(int(arguments["offset"]), 0)
    sev = arguments.get("findings_severity") or arguments.get("severity")
    if sev is not None and str(sev).strip():
        body["findings_severity"] = str(sev).strip()

    status_code, data = request("POST", "/api/v1/resolve-scan", json_body=body, timeout=60.0)
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)

    st = ssc_status(data if isinstance(data, dict) else None)
    scan_id = data.get("scan_id") or data.get("id") if isinstance(data, dict) else None
    defer = st in ("started", "scanning", "queued", "running", "pending")
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "base_url": base_url(),
            "repo_url": repo_url,
            "branch": branch or None,
            "status": st,
            "scan_id": scan_id,
            "defer": defer,
            "end_run_recommended": defer,
            "target_id": data.get("target_id") if isinstance(data, dict) else None,
            "commit_sha": data.get("commit_sha") if isinstance(data, dict) else None,
            "status_poll_path": data.get("status_poll_path") if isinstance(data, dict) else None,
            "findings_poll_path": data.get("findings_poll_path") if isinstance(data, dict) else None,
            "progress": data.get("progress") if isinstance(data, dict) else None,
            "summary": data.get("summary") if isinstance(data, dict) else None,
            "pagination": data.get("pagination") if isinstance(data, dict) else None,
            "findings": normalize_findings(data) if st == "ready" else [],
            "response": data,
            "agent_guidance": agent_guidance_for_status(st),
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_resolve": security_scan_resolve,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_resolve",
            "TOOL_DESCRIPTION": (
                "Primary SimpleSecCheck entry: resolve or enqueue scan for a Git repo. "
                "Returns status ready|scanning|started and scan_id. If started/scanning, end the run."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "HTTPS Git URL; omitted = workspace origin",
                    },
                    "branch": {"type": "string", "TOOL_DESCRIPTION": "Branch (default main)"},
                    "check_commit": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Skip new scan when remote HEAD unchanged (default true)",
                    },
                    "force_scan": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Always enqueue a new scan (default false)",
                    },
                    "findings_limit": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": f"Max findings when status=ready (1–{MAX_FINDINGS_LIMIT})",
                    },
                    "findings_offset": {"type": "integer", "TOOL_DESCRIPTION": "Findings pagination offset"},
                    "findings_severity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "e.g. CRITICAL,HIGH when status=ready",
                    },
                },
            },
        },
    },
]
