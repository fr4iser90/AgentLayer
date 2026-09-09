"""Chat tool: prompt the Web UI to collect a user secret (authenticated card, no OTP curl)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.infrastructure.platform.config import config
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.identity.secret_otp_bundle import validate_user_secret_service_key
from apps.backend.infrastructure.identity.user_secret_forms import form_spec_for_service_key
from plugins.tools.platform.secrets.save_user_secret import _catalog_service_keys

__version__ = "1.1.0"
TOOL_ID = "request_user_secret"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Request user secret (UI)"
TOOL_DESCRIPTION = (
    "Show an in-chat form so the signed-in user can save a credential (Web UI). "
    "service_key: catalog keys when declared (e.g. github_pat), otherwise derive from "
    "the env/var name (FOO_BAR → foo_bar). Any signed-in user can save their own secrets — "
    "admin role is not required. Not for OTP/curl (use register_secrets for headless)."
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
                    "AGENT_SECRETS_MASTER_KEY fehlt (Operator/.env) — "
                    "das ist keine Benutzer-/Admin-Berechtigung."
                ),
                "not_a_permission_error": True,
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
                "error": "invalid service_key (lowercase [a-z0-9._-], max 63 chars)",
                "catalog_service_keys": _catalog_service_keys(),
                "hint": (
                    "Prefer a catalog key when available. For project env vars, derive "
                    "service_key by lowercasing the env name (FOO_BAR → foo_bar)."
                ),
            },
            ensure_ascii=False,
        )
    catalog = _catalog_service_keys()
    in_catalog = bool(catalog) and sk in catalog
    reason = (arguments.get("reason") or "").strip()
    spec = form_spec_for_service_key(sk) or {}
    title = (spec.get("title") or sk).strip() if isinstance(spec.get("title"), str) else sk
    help_text = spec.get("help") if isinstance(spec.get("help"), str) else None
    fields = spec.get("fields") if isinstance(spec.get("fields"), list) else []
    if not fields:
        fields = [
            {
                "name": "secret",
                "label": "Secret",
                "type": "password",
                "required": True,
            }
        ]
        if not help_text:
            help_text = (
                f"Credential slot `{sk}`"
                + (" (custom project key)." if not in_catalog else ".")
            )
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
            "catalog_key": in_catalog,
            "secret_prompt": secret_prompt,
            "for_assistant_must_say_de": (
                "Eine Eingabe-Card erscheint im Chat — der Nutzer trägt das Secret ein und klickt Speichern. "
                "Kein curl. Secret nicht wiederholen. Nach Speichern: user_secrets_status. "
                "Admin-Rolle ist nicht nötig — jeder angemeldete User speichert seine eigenen Secrets."
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
                "service_key: catalog key if declared, else derive from env/var name "
                "(FOO_BAR → foo_bar). Optional: reason. Not a role check — any signed-in user. "
                "Do NOT use register_secrets/curl in the Web UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Secret slot (lowercase [a-z0-9._-]); catalog key or "
                            "lowercased env name for project credentials."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional short reason shown on the card.",
                    },
                },
                "required": ["service_key"],
            },
        },
    },
]
