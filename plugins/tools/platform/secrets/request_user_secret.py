"""Chat tool: prompt the Web UI to collect a user secret (authenticated card, no OTP curl)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.secret_otp_bundle import validate_user_secret_service_key
from apps.backend.infrastructure.user_secret_forms import form_spec_for_service_key
from plugins.tools.platform.secrets.save_user_secret import _catalog_service_keys

__version__ = "1.0.0"
TOOL_ID = "request_user_secret"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Request user secret (UI)"
TOOL_DESCRIPTION = (
    "Show an in-chat form so the signed-in user can save a credential (Web UI). "
    "Use when a secret is missing or invalid — not for OTP/curl (use register_secrets for headless)."
)
# Router phrases: co-located request_user_secret.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("secrets.user",)


def request_user_secret(arguments: dict[str, Any]) -> str:
    if not (config.SECRETS_MASTER_KEY or "").strip():
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Speichern ist auf dem Server nicht aktiviert: "
                    "AGENT_SECRETS_MASTER_KEY fehlt."
                ),
            },
            ensure_ascii=False,
        )
    _tid, uid = get_identity()
    if uid is None:
        return json.dumps(
            {"ok": False, "error": "not authenticated — Web UI sign-in required"},
            ensure_ascii=False,
        )
    sk = validate_user_secret_service_key(arguments.get("service_key"))
    if not sk:
        return json.dumps(
            {
                "ok": False,
                "error": "invalid service_key",
                "catalog_service_keys": _catalog_service_keys(),
            },
            ensure_ascii=False,
        )
    catalog = _catalog_service_keys()
    if catalog and sk not in catalog:
        return json.dumps(
            {
                "ok": False,
                "error": f"unknown service_key (not in tool catalog): {sk!r}",
                "catalog_service_keys": catalog,
            },
            ensure_ascii=False,
        )
    reason = (arguments.get("reason") or "").strip()
    spec = form_spec_for_service_key(sk) or {}
    title = (spec.get("title") or sk).strip() if isinstance(spec.get("title"), str) else sk
    help_text = spec.get("help") if isinstance(spec.get("help"), str) else None
    fields = spec.get("fields") if isinstance(spec.get("fields"), list) else []
    prompt_id = str(uuid.uuid4())
    secret_prompt: dict[str, Any] = {
        "prompt_id": prompt_id,
        "service_key": sk,
        "mode": "authenticated",
        "title": title,
        "help": help_text,
        "fields": fields,
        "reason": reason or None,
    }
    return json.dumps(
        {
            "ok": True,
            "ui_emitted": True,
            "prompt_id": prompt_id,
            "service_key": sk,
            "secret_prompt": secret_prompt,
            "for_assistant_must_say_de": (
                "Eine Eingabe-Card erscheint im Chat — der Nutzer trägt das Secret ein und klickt Speichern. "
                "Kein curl. Secret nicht wiederholen. Nach Speichern: user_secrets_status oder Scan erneut versuchen."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "request_user_secret": request_user_secret,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "request_user_secret",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": (
                "Show the in-chat secret registration card (Web UI, signed-in user). "
                "Required: service_key from TOOL_SECRETS_REQUIRED (e.g. ssc_api_key). "
                "Optional: reason (short subtitle). Do NOT use register_secrets/curl when the user is in the Web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Integration secret slot (lowercase [a-z0-9._-]); "
                            "must match TOOL_SECRETS_REQUIRED on the consuming tool."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional short reason shown on the card (e.g. SSC key expired).",
                    },
                },
                "required": ["service_key"],
            },
        },
    },
]
