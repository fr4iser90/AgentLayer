"""POST /api/v1/scans/ — low-level scan enqueue."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    END_RUN_GUIDANCE,
    agent_guidance_for_status,
    dump_ok,
    request,
    resolve_repo_url,
    ssc_domain_attrs,
    ssc_status,
)
from apps.backend.domain.async_wait import parse_estimated_time_seconds
from apps.backend.domain.security_scan.deferred import (
    invoke_scan_deferred_wait,
    merge_wait_into_payload,
    should_wait_for_scan,
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
# Router phrases: co-located start.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
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
    api_data = data if isinstance(data, dict) else None
    scan_id = api_data.get("id") or api_data.get("scan_id") if api_data else None
    st = ssc_status(api_data)
    estimated_sec = parse_estimated_time_seconds(api_data)
    defer = st in ("started", "scanning", "queued", "running", "pending") or st is None
    payload: dict[str, Any] = {
        "ok": True,
        "http_status": status_code,
        "scan_id": scan_id,
        "status": st,
        "estimated_time_seconds": estimated_sec,
        "repo_url": repo_url,
        "branch": branch or None,
        "scan": data,
        "defer": defer,
        "end_run_recommended": defer,
        "agent_guidance": agent_guidance_for_status(st, data=api_data)
        if st
        else [END_RUN_GUIDANCE],
    }
    if (
        scan_id
        and should_wait_for_scan(
            arguments,
            context,
            st=st,
            estimated_sec=estimated_sec,
            scan_id=str(scan_id),
        )
    ):
        wait_result = invoke_scan_deferred_wait(
            str(scan_id),
            estimated_sec=estimated_sec,
            context=context,
            initial_status=st,
            arguments=arguments,
        )
        merge_wait_into_payload(payload, wait_result=wait_result, api_data=api_data)
    return dump_ok(payload)


HANDLERS: dict[str, Callable[..., str]] = {
    "start": start,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "start",
            "TOOL_DESCRIPTION": (
                "Low-level scan enqueue (POST /api/v1/scans/). Prefer security_scan_resolve. "
                "Returns estimated_time_seconds when available; wait_for_completion polls until done."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "TOOL_DESCRIPTION": "HTTPS Git clone URL"},
                    "branch": {"type": "string", "TOOL_DESCRIPTION": "Branch name"},
                    "scan_type": {"type": "string", "TOOL_DESCRIPTION": "Optional scan profile"},
                    "wait_for_completion": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Poll until scan completes when estimate is available",
                    },
                    "skip_scan_wait": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Benchmark only: skip auto-wait even when estimate exists",
                    },
                },
            },
        },
    },
]
