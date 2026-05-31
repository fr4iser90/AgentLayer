"""GET /api/v1/scans/{id}/findings — paginated findings."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.integrations.simple_sec_check.ssc_common import (
    DEFAULT_FINDINGS_LIMIT,
    END_RUN_GUIDANCE,
    MAX_FINDINGS_LIMIT,
    NO_WAIT_SUFFIX,
    agent_guidance_for_status,
    dump_ok,
    findings_query_params,
    merge_agent_guidance,
    normalize_findings,
    request,
    split_path_query,
    ssc_domain_attrs,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_findings"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: findings"
TOOL_DESCRIPTION = "Paginated security findings for a completed scan."
TOOL_TRIGGERS = ("scan findings", "vulnerabilities", "semgrep findings")

_FINDINGS_PARAMS = {
    "scan_id": {
        "type": "string",
        "TOOL_DESCRIPTION": "Scan UUID from resolve/status/callback",
    },
    "poll_path": {
        "type": "string",
        "TOOL_DESCRIPTION": "Relative findings_poll_path or pagination.next_path from resolve/findings",
    },
    "limit": {
        "type": "integer",
        "TOOL_DESCRIPTION": f"Page size 1–{MAX_FINDINGS_LIMIT} (default {DEFAULT_FINDINGS_LIMIT})",
    },
    "offset": {"type": "integer", "TOOL_DESCRIPTION": "Pagination offset (default 0)"},
    "severity": {
        "type": "string",
        "TOOL_DESCRIPTION": "Comma-separated severities, e.g. CRITICAL,HIGH",
    },
    "findings_severity": {
        "type": "string",
        "TOOL_DESCRIPTION": "Alias for severity filter",
    },
}


def security_scan_findings(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    poll_path = str(arguments.get("poll_path") or arguments.get("findings_poll_path") or "").strip()
    scan_id = str(arguments.get("scan_id") or arguments.get("id") or "").strip()
    explicit_params = findings_query_params(arguments)

    if poll_path:
        path, q = split_path_query(poll_path)
        merged = {**q, **explicit_params}
        status_code, data = request("GET", path, params=merged or None)
    elif scan_id:
        params = dict(explicit_params)
        if not params.get("limit"):
            params["limit"] = DEFAULT_FINDINGS_LIMIT
        status_code, data = request(
            "GET", f"/api/v1/scans/{scan_id}/findings", params=params or None
        )
    else:
        return dump_ok(
            {"ok": False, "error": "scan_id or poll_path (findings_poll_path) is required"}
        )

    if isinstance(data, dict) and data.get("ok") is False:
        if data.get("retry_later"):
            data["agent_guidance"] = merge_agent_guidance(
                data.get("agent_guidance") or [],
                ["Scan not ready yet. " + END_RUN_GUIDANCE],
            )
        return dump_ok(data)

    cap = None
    if poll_path:
        _, qmerge = split_path_query(poll_path)
        cap = explicit_params.get("limit") or qmerge.get("limit")
    else:
        cap = explicit_params.get("limit") or DEFAULT_FINDINGS_LIMIT
    if cap is not None:
        cap = int(cap)
    findings = normalize_findings(data, cap=cap)
    pagination = data.get("pagination") if isinstance(data, dict) else None
    summary = data.get("summary") if isinstance(data, dict) else None
    sid = scan_id or (data.get("scan_id") if isinstance(data, dict) else None)

    api_data = data if isinstance(data, dict) else None
    pagination_hint: list[str] = []
    if isinstance(pagination, dict) and pagination.get("has_more"):
        pagination_hint = [
            "pagination.has_more is true — call security_scan_findings again in this or a later "
            "run with offset or pagination.next_path; do not poll until scan completes."
        ]

    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "scan_id": sid,
            "finding_count": len(findings),
            "findings": findings,
            "summary": summary,
            "pagination": pagination,
            "response": data,
            "agent_guidance": agent_guidance_for_status(
                None,
                data=api_data,
                findings=findings,
                extra=pagination_hint or None,
            ),
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_findings": security_scan_findings,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_findings",
            "TOOL_DESCRIPTION": (
                "Paginated findings for a completed scan (summary + pagination). "
                "409 if scan still running — end run and retry later."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {"type": "object", "properties": dict(_FINDINGS_PARAMS)},
        },
    },
]
