"""Chat tool: mint OTP and return bash-safe curl for POST /v1/user/secrets/register-with-otp."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.core.config import config
from apps.backend.infrastructure.secret_otp_bundle import secret_otp_bundle

__version__ = "1.0.0"
TOOL_ID = "register_secrets"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Secrets"
TOOL_DESCRIPTION = (
    "Register per-user credentials with OTP + curl; static help for stored secrets. "
    "In the Agent web UI, **Settings → Connections** can save the same secrets (schema-driven forms) when signed in."
)
TOOL_TRIGGERS = (
    "secret",
    "credential",
    "api key",
    "app password",
    "otp",
    "register_secret",
)
TOOL_CAPABILITIES = ("secrets.user",)


def register_secrets(arguments: dict[str, Any]) -> str:
    """
    Mint a one-time code bound to the current chat user; return a bash-safe curl that only needs
    the secret placeholder replaced (no Bearer / user headers for the end user).
    """
    if not config.SECRETS_MASTER_KEY:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Speichern ist auf dem Server nicht aktiviert: Betreiber muss einmalig "
                    "AGENT_SECRETS_MASTER_KEY in docker/.env setzen (Verschlüsselung in Postgres — "
                    "Endnutzer tragen das nie ein). Siehe TOOLS.md."
                ),
            },
            ensure_ascii=False,
        )
    raw_svc = secret_otp_bundle.normalize_service_key(
        arguments.get("service_key_example")
    )
    ttl = secret_otp_bundle.ttl_clamp(arguments.get("ttl_seconds"))
    payload = secret_otp_bundle.build_otp_curl_payload(raw_svc, ttl)
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "register_secrets": register_secrets,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "register_secrets",
            "TOOL_DESCRIPTION": (
                "ONLY way to get a valid OTP and curl for saving a user secret. You MUST invoke this tool — "
                "NEVER invent or type a curl command yourself (wrong OTP, wrong JSON, broken quotes). "
                "Copy to the user ONLY the exact curl_bash string from YOUR tool response JSON (and jq_register_example_de if present). "
                "Match service_key_example to what the user asked for: Google Calendar iCal URL → google_calendar; Gmail → gmail; GitHub PAT → github_pat; generic ICS → calendar_ics. "
                "Always include for_assistant_must_say_de: secret is NOT stored until the user runs that curl/jq and gets stored:true. "
                "Do NOT pretty-print curl_bash. Never paste real secrets or iCal URLs into chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key_example": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Must match the integration: google_calendar or calendar_ics (HTTPS ICS URL JSON with ics_url), "
                            "gmail (IMAP: email + app_password JSON), github_pat (token JSON {\"token\":\"ghp_…\"}). "
                            "Lowercase [a-z0-9._-]."
                        ),
                    },
                    "ttl_seconds": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Optional OTP lifetime 120–3600 (default 600).",
                    },
                },
            },
        },
    },
]
