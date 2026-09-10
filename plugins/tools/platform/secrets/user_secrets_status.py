"""List configured user secret keys (no values) for the signed-in chat user."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.infrastructure.platform.config import config
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db import db
from plugins.tools.workspace.lib.common import workspace_id_from_context

__version__ = "1.1.0"
TOOL_ID = "user_secrets_status"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "User secrets status"
TOOL_DESCRIPTION = (
    "List which secret service_key slots are already stored (no secret values). "
    "Returns global keys plus workspace-scoped keys when a project is bound. "
    "Use before asking the user to paste API keys."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("secrets.user",)


def _catalog_keys() -> list[str]:
    try:
        from plugins.tools.platform.secrets.save_user_secret import (
            _catalog_service_keys,
        )

        return _catalog_service_keys()
    except Exception:
        return []


def user_secrets_status(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not (config.SECRETS_MASTER_KEY or "").strip():
        return json.dumps(
            {
                "ok": True,
                "storage_enabled": False,
                "configured": [],
                "configured_global": [],
                "configured_workspace": [],
                "catalog_keys": _catalog_keys(),
                "hint": "AGENT_SECRETS_MASTER_KEY not set; only operator env fallbacks may apply.",
            },
            ensure_ascii=False,
        )
    _tid, uid = get_identity()
    if uid is None:
        return json.dumps({"ok": False, "error": "not authenticated"}, ensure_ascii=False)

    arg_wid = str(arguments.get("workspace_id") or "").strip() or None
    wid = arg_wid or workspace_id_from_context(context)

    configured_global = sorted(db.user_secret_list_service_keys(uid))
    configured_workspace: list[str] = []
    if wid:
        try:
            import uuid as _uuid

            configured_workspace = sorted(
                db.user_workspace_secret_list_service_keys(uid, _uuid.UUID(str(wid)))
            )
        except Exception:
            configured_workspace = []

    # Union for backwards-compatible ``configured`` field.
    configured = sorted(set(configured_global) | set(configured_workspace))
    catalog = _catalog_keys()
    missing = [k for k in catalog if k not in configured_global]
    return json.dumps(
        {
            "ok": True,
            "storage_enabled": True,
            "configured": configured,
            "configured_global": configured_global,
            "configured_workspace": configured_workspace,
            "workspace_id": wid,
            "catalog_keys": catalog,
            "missing_from_catalog": missing,
            "for_assistant": (
                "Do not ask the user to paste keys listed under configured_global / "
                "configured_workspace. Project env vars use workspace scope + env_bindings."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "user_secrets_status": user_secrets_status,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "user_secrets_status",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional workspace UUID; defaults to the bound workspace."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]
