"""GET /api/user/targets — list My Targets."""

from __future__ import annotations

from typing import Any, Callable

from apps.backend.domain.security_scan.common import (
    NO_WAIT_SUFFIX,
    base_url,
    dump_ok,
    request,
    ssc_domain_attrs,
)

__version__ = "1.1.0"
_attrs = ssc_domain_attrs()
TOOL_ID = "ssc_targets"
TOOL_BUCKET = _attrs["TOOL_BUCKET"]
TOOL_DOMAIN = _attrs["TOOL_DOMAIN"]
TOOL_CAPABILITIES = _attrs["TOOL_CAPABILITIES"]
TOOL_SECRETS_REQUIRED = _attrs["TOOL_SECRETS_REQUIRED"]
TOOL_USER_SECRET_FORMS = _attrs["TOOL_USER_SECRET_FORMS"]
TOOL_LABEL = "SimpleSecCheck: targets"
TOOL_DESCRIPTION = "List SimpleSecCheck My Targets registrations."
# Router phrases: co-located targets_list.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
def targets_list(arguments: dict[str, Any], context: dict | None = None) -> str:
    _ = context
    status_code, data = request("GET", "/api/user/targets")
    if isinstance(data, dict) and data.get("ok") is False:
        return dump_ok(data)
    targets: list[dict[str, Any]] = []
    if isinstance(data, list):
        targets = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("targets", "items", "data", "results"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                targets = [x for x in chunk if isinstance(x, dict)]
                break
    return dump_ok(
        {
            "ok": True,
            "http_status": status_code,
            "base_url": base_url(),
            "count": len(targets),
            "targets": targets,
        }
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "targets_list": targets_list,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "targets_list",
            "TOOL_DESCRIPTION": "List SimpleSecCheck My Targets (repo registrations)." + NO_WAIT_SUFFIX,
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
