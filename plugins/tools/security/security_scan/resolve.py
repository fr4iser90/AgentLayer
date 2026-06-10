"""POST /api/v1/resolve-scan — primary SimpleSecCheck entry."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    DEFAULT_FINDINGS_LIMIT,
    MAX_FINDINGS_LIMIT,
    NO_WAIT_SUFFIX,
    agent_guidance_for_status,
    base_url,
    bool_arg,
    dump_ok,
    merge_agent_guidance,
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
# Router phrases: co-located resolve.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def resolve(arguments: dict[str, Any], context: dict | None = None) -> str:
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

    api_data = data if isinstance(data, dict) else None
    st = ssc_status(api_data)
    scan_id = api_data.get("scan_id") or api_data.get("id") if api_data else None
    defer = st in ("started", "scanning", "queued", "running", "pending")
    findings = normalize_findings(api_data) if st == "ready" else []
    payload: dict[str, Any] = {
        "ok": True,
        "http_status": status_code,
        "base_url": base_url(),
        "repo_url": repo_url,
        "branch": branch or None,
        "status": st,
        "scan_id": scan_id,
        "defer": defer,
        "end_run_recommended": defer,
        "target_id": api_data.get("target_id") if api_data else None,
        "commit_sha": api_data.get("commit_sha") if api_data else None,
        "status_poll_path": api_data.get("status_poll_path") if api_data else None,
        "findings_poll_path": api_data.get("findings_poll_path") if api_data else None,
        "progress": api_data.get("progress") if api_data else None,
        "summary": api_data.get("summary") if api_data else None,
        "pagination": api_data.get("pagination") if api_data else None,
        "findings": findings,
        "response": data,
        "agent_guidance": agent_guidance_for_status(
            st, data=api_data, findings=findings
        ),
    }
    if st == "ready" and scan_id:
        from apps.backend.domain.ssc_scan_artifact import maybe_persist_ssc_scan_artifact

        sev = str(arguments.get("findings_severity") or arguments.get("severity") or "").strip()
        artifact_id = maybe_persist_ssc_scan_artifact(
            context,
            scan_id=str(scan_id),
            summary=payload.get("summary"),
            findings=findings,
            repo_url=repo_url,
            branch=branch or None,
            severity_filter=sev or None,
        )
        if artifact_id:
            payload["artifact_id"] = artifact_id
            payload["agent_guidance"] = merge_agent_guidance(
                payload.get("agent_guidance") or [],
                [
                    f"Scan artifact persisted: artifact_id={artifact_id}. "
                    "Parent should pass this to agent_delegate artifact_refs when delegating fixes to coding."
                ],
            )
    return dump_ok(payload)


HANDLERS: dict[str, Callable[..., str]] = {
    "resolve": resolve,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resolve",
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
