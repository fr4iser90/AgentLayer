"""GET /api/v1/finding-policy/schema — scanner policy JSON shape (no scan_id)."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    NO_WAIT_SUFFIX,
    base_url,
    dump_ok,
    request,
    ssc_domain_attrs,
)

__version__ = "1.0.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_policy_schema"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: policy schema"
TOOL_DESCRIPTION = "Fetch finding-policy JSON schema from SimpleSecCheck (per-tool field rules)."
# Router phrases: co-located finding_policy_schema.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def _guidance_from_api(data: dict[str, Any]) -> list[str]:
    raw = data.get("agent_guidance")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _tools_query_param(arguments: dict[str, Any]) -> str | None:
    raw = arguments.get("tools")
    if raw is None:
        return None
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
        return ",".join(parts) if parts else None
    s = str(raw).strip()
    return s or None


def finding_policy_schema(
    arguments: dict[str, Any], context: dict | None = None
) -> str:
    _ = context
    params: dict[str, Any] = {}
    tools = _tools_query_param(arguments)
    if tools:
        params["tools"] = tools
    status_code, data = request(
        "GET", "/api/v1/finding-policy/schema", params=params or None, timeout=30.0
    )
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)
    schema = data
    notes = None
    agent_guidance: list[str] = []
    if isinstance(data, dict):
        if "schema" in data and isinstance(data["schema"], dict):
            schema = data["schema"]
        notes = data.get("notes")
        agent_guidance = _guidance_from_api(data)
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "base_url": base_url(),
            "tools_filter": tools,
            "schema": schema,
            "notes": notes,
            "agent_guidance": agent_guidance,
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "finding_policy_schema": finding_policy_schema,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "finding_policy_schema",
            "TOOL_DESCRIPTION": (
                "GET SimpleSecCheck finding-policy schema (per-tool accepted_findings fields). "
                "No scan_id. Follow agent_guidance and notes in the tool response (from SSC). "
                "Optional tools filter (e.g. semgrep,gitleaks)."
                + NO_WAIT_SUFFIX
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Comma-separated tool names (query ?tools=); omit for full schema"
                        ),
                    },
                },
            },
        },
    },
]
