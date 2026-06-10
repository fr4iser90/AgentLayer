"""List configured user secret keys (no values) for the signed-in chat user."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "user_secrets_status"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "User secrets status"
TOOL_DESCRIPTION = (
    "List which per-user secret service_key slots are already stored (no secret values). "
    "Use before asking the user to paste API keys."
)
# Router phrases: co-located user_secrets_status.router.yaml (all locales unioned at load).
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


def user_secrets_status(arguments: dict[str, Any]) -> str:
    _ = arguments
    if not (config.SECRETS_MASTER_KEY or "").strip():
        return json.dumps(
            {
                "ok": True,
                "storage_enabled": False,
                "configured": [],
                "catalog_keys": _catalog_keys(),
                "hint": "AGENT_SECRETS_MASTER_KEY not set; only operator env fallbacks may apply.",
            },
            ensure_ascii=False,
        )
    _tid, uid = get_identity()
    if uid is None:
        return json.dumps({"ok": False, "error": "not authenticated"}, ensure_ascii=False)
    configured = sorted(db.user_secret_list_service_keys(uid))
    catalog = _catalog_keys()
    missing = [k for k in catalog if k not in configured]
    return json.dumps(
        {
            "ok": True,
            "storage_enabled": True,
            "configured": configured,
            "catalog_keys": catalog,
            "missing_from_catalog": missing,
            "for_assistant": (
                "Do not ask the user to paste keys listed under configured. "
                "For SSC use security_auditor delegate after workspace bind."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "user_secrets_status": user_secrets_status,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "user_secrets_status",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
