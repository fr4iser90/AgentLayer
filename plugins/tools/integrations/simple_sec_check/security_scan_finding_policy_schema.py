"""GET /api/v1/finding-policy/schema — scanner policy JSON shape (no scan_id)."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.integrations.simple_sec_check.ssc_common import (
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
TOOL_TRIGGERS = ("finding-policy", "policy schema", "ssc schema")

_POLICY_SCHEMA_GUIDANCE = [
    "Call once per agent session before editing .scanning/finding-policy.json; reuse the cached schema.",
    "Workflow: schema → security_scan_resolve (findings) → merge policy (validate fields per tool) → fixes → security_scan_agent_callback.",
    "Scanner ignores root-level dedupe in repo policy; only semgrep.dedupe (and semgrep.severity_overrides) apply.",
]


def _tools_query_param(arguments: dict[str, Any]) -> str | None:
    raw = arguments.get("tools")
    if raw is None:
        return None
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
        return ",".join(parts) if parts else None
    s = str(raw).strip()
    return s or None


def security_scan_finding_policy_schema(
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
    if isinstance(data, dict):
        if "schema" in data and isinstance(data["schema"], dict):
            schema = data["schema"]
        notes = data.get("notes")
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "base_url": base_url(),
            "tools_filter": tools,
            "schema": schema,
            "notes": notes,
            "agent_guidance": list(_POLICY_SCHEMA_GUIDANCE),
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_finding_policy_schema": security_scan_finding_policy_schema,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_finding_policy_schema",
            "TOOL_DESCRIPTION": (
                "GET SimpleSecCheck finding-policy schema (per-tool accepted_findings fields). "
                "No scan_id. Call once per session before resolve-scan when updating "
                ".scanning/finding-policy.json; optional tools filter (e.g. semgrep,gitleaks)."
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
