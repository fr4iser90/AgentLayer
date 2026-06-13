"""GET /api/v1/scans/ — list recent scans."""

from __future__ import annotations

import builtins
from typing import Any, Callable

from plugins.tools.security.security_scan.common import (
    NO_WAIT_SUFFIX,
    base_url,
    dump_ok,
    normalize_scan_list,
    request,
    ssc_domain_attrs,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_list"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: list scans"
TOOL_DESCRIPTION = "List recent SimpleSecCheck scans."
# Router phrases: co-located list.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def list(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    limit = min(max(int(arguments.get("limit") or 10), 1), 50)
    status_code, data = request("GET", "/api/v1/scans/", params={"limit": limit})
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)
    scans = normalize_scan_list(data)
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "base_url": base_url(),
            "count": len(scans),
            "scans": scans,
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "list": list,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list",
            "TOOL_DESCRIPTION": "List recent scans (debug/history)." + NO_WAIT_SUFFIX,
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Max scans (1–50, default 10)",
                    },
                },
            },
        },
    },
]
