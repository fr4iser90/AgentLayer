"""Chat tool: store a per-user encrypted secret directly (no OTP curl)."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.secret_otp_bundle import validate_user_secret_service_key

__version__ = "1.0.0"
TOOL_ID = "save_user_secret"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Secrets"
TOOL_DESCRIPTION = (
    "Store a per-user credential for the signed-in chat user (encrypted in Postgres). "
    "Use when the user pasted a credential in chat and asked to save it. "
    "service_key must match the integration tool's TOOL_SECRETS_REQUIRED / Connections catalog entry."
)
# Router phrases: co-located save_user_secret.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("secrets.user",)


def _catalog_service_keys() -> list[str]:
    """Keys declared by integration tools (TOOL_SECRETS_REQUIRED / user_secret_forms)."""
    try:
        from apps.backend.domain.plugin_system.registry import get_registry

        keys: set[str] = set()
        for row in get_registry().tools_meta:
            for k in row.get("secrets_required") or []:
                sk = str(k).strip().lower()
                if sk:
                    keys.add(sk)
            for k in (row.get("user_secret_forms") or {}):
                sk = str(k).strip().lower()
                if sk:
                    keys.add(sk)
        return sorted(keys)
    except Exception:
        return []


def _coerce_secret_body(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str):
        s = raw.strip()
        return s or None
    return None


def save_user_secret(arguments: dict[str, Any]) -> str:
    if not config.SECRETS_MASTER_KEY:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Speichern ist auf dem Server nicht aktiviert: Betreiber muss "
                    "AGENT_SECRETS_MASTER_KEY in docker/.env setzen."
                ),
            },
            ensure_ascii=False,
        )
    _tid, uid = get_identity()
    if uid is None:
        return json.dumps(
            {
                "ok": False,
                "error": "no user identity — sign in so the secret binds to your account",
            },
            ensure_ascii=False,
        )
    sk = validate_user_secret_service_key(arguments.get("service_key"))
    if not sk:
        return json.dumps(
            {
                "ok": False,
                "error": "invalid service_key (lowercase [a-z0-9._-], max 63 chars)",
                "catalog_service_keys": _catalog_service_keys(),
                "hint": (
                    "Use the service_key from the integration tool that needs the credential "
                    "(TOOL_SECRETS_REQUIRED / Settings → Connections), not a made-up name."
                ),
            },
            ensure_ascii=False,
        )
    secret = _coerce_secret_body(arguments.get("secret"))
    if not secret:
        return json.dumps(
            {"ok": False, "error": "secret is required (string or JSON object)"},
            ensure_ascii=False,
        )
    if len(secret) > 65536:
        return json.dumps(
            {"ok": False, "error": "secret too large (max 65536 chars)"},
            ensure_ascii=False,
        )
    try:
        db.user_secret_upsert(uid, sk, secret)
    except RuntimeError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "stored": True,
            "service_key": sk,
            "for_assistant_must_say_de": (
                "Secret wurde gespeichert. Den Klartext **nicht** wiederholen oder zitieren."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "save_user_secret": save_user_secret,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_user_secret",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": (
                "Store a user secret immediately (no OTP curl). Use when the user pasted a credential in chat "
                "and asked to save it. Required: service_key (from the target integration tool schema / "
                "Connections catalog) and secret (plain string or JSON). Never echo the secret value back."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Integration secret slot name (lowercase [a-z0-9._-]); "
                            "must match TOOL_SECRETS_REQUIRED on the tool that will consume it."
                        ),
                    },
                    "secret": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Credential to store (plain string or JSON object as string)."
                        ),
                    },
                },
                "required": ["service_key", "secret"],
            },
        },
    },
]
