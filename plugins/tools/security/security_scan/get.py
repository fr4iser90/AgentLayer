"""Alias for security_scan_status."""

from __future__ import annotations

from typing import Any, Callable

from plugins.tools.security.security_scan.status import status
from apps.backend.domain.security_scan.common import NO_WAIT_SUFFIX, ssc_domain_attrs

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
# Router phrases: co-located get.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def get(arguments: dict[str, Any], context: dict | None = None) -> str:
    return status(arguments, context)


HANDLERS: dict[str, Callable[..., str]] = {
    "get": get,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get",
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
