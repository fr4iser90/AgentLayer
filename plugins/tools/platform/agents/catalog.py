"""List registered agents with domains and capabilities (orchestrator discovery)."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.agent_runtime.catalog import build_agents_catalog
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "agents_catalog"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "platform"
# Router phrases: co-located catalog.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("meta.agents.read",)
TOOL_LABEL = "Agent catalog"
TOOL_DESCRIPTION = (
    "List specialist agents for delegate routing. Delegatable agents include tool_names "
    "(their allowlist). Use delegatable_only=true before delegate. Admins may set "
    "include_tool_names=true for effective_tool_names per caller."
)


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def catalog(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    _tid, uid = get_identity()
    role = db.user_role(uid) if uid is not None else "user"
    tenant_id = int(db.user_tenant_id(uid) or 1) if uid is not None else 1
    if context:
        ctx_role = context.get("user_role") or context.get("role")
        if isinstance(ctx_role, str) and ctx_role.strip():
            role = ctx_role.strip().lower()

    payload = build_agents_catalog(
        user_role=role,
        tenant_id=tenant_id,
        delegatable_only=_truthy(arguments.get("delegatable_only")),
        include_tool_names=_truthy(arguments.get("include_tool_names")),
    )
    return json.dumps(payload, ensure_ascii=False)


HANDLERS: dict[str, Callable[..., str]] = {
    "catalog": catalog,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "catalog",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "delegatable_only": {
                        "type": "boolean",
                        "description": "If true, only agents reachable via delegate (specialists).",
                    },
                    "include_tool_names": {
                        "type": "boolean",
                        "description": "Admin only: include tool_names and effective_tool_names per agent.",
                    },
                },
            },
        },
    },
]
