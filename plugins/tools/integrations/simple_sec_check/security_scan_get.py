"""Alias for security_scan_status."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.integrations.simple_sec_check.security_scan_status import security_scan_status
from plugins.tools.integrations.simple_sec_check.ssc_common import NO_WAIT_SUFFIX, ssc_domain_attrs

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_get"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: get"
TOOL_DESCRIPTION = "Alias for security_scan_status."
TOOL_TRIGGERS = ("scan get", "simplesec get")


def security_scan_get(arguments: dict[str, Any], context: dict | None = None) -> str:
    return security_scan_status(arguments, context)


HANDLERS: dict[str, Callable[..., str]] = {
    "security_scan_get": security_scan_get,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "security_scan_get",
            "TOOL_DESCRIPTION": "Alias for security_scan_status." + NO_WAIT_SUFFIX,
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
