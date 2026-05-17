"""Static help for user secrets (no OTP); use register_secrets tool for OTP + curl."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.core.config import config
from apps.backend.infrastructure.db import db
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.secret_otp_bundle import secret_otp_bundle

__version__ = "1.0.0"
TOOL_ID = "secrets_help"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_TRIGGERS = ()
TOOL_CAPABILITIES = ("secrets.user",)


def secrets_help(arguments: dict[str, Any]) -> str:
    """Static help for user secrets: OTP only via register_secrets; no OTP is minted here."""
    raw_svc = secret_otp_bundle.normalize_service_key(
        arguments.get("service_key_example")
    )
    topic = (arguments.get("topic") or "").strip().lower()

    base = config.PUBLIC_BASE_URL or f"http://127.0.0.1:{config.HTTP_EXAMPLE_PORT}"
    auth_identity = (
        "Use Authorization: Bearer <JWT from POST /auth/login or a user API key>; "
        "user/tenant come from the token (users.tenant_id), not from X-* identity headers."
    )

    _tid, uid = get_identity()
    resolved_sub = db.user_external_sub(uid) if uid is not None else None
    user_value = resolved_sub if resolved_sub is not None else "DEINE_WEBUI_USER_ID"

    hints: list[str] = [
        "Neues Secret speichern: **nur** Tool `register_secrets` — in der Antwort stehen `curl_bash` und ggf. `jq_register_example_de` (OTP ist schon eingebaut).",
        "Mit Web-UI (eingeloggt): **Einstellungen → Connections** — dort zeigen die Tools die passenden Felder (Gmail, GitHub, Kalender …).",
        "Dieses Tool (`secrets_help`) erzeugt **kein** OTP und keinen curl — nur Erklärung.",
    ]
    if topic in ("email", "imap", "mail", "gmail"):
        hints.append(
            "Gmail: **App-Passwort** (nicht das normale Passwort); `service_key` **`gmail`** — JSON `{\"email\":\"…\",\"app_password\":\"…\"}` oder Formular unter Einstellungen → Connections."
        )
    if topic in ("github", "gh", "pat"):
        hints.append(
            'GitHub: `service_key` **`github_pat`** — JSON `{"token":"ghp_…"}` (oder nur den Token-String). Operator kann stattdessen `GITHUB_TOKEN` in docker/.env setzen.'
        )
    if topic in ("ssc", "simplesec", "simple_sec", "security_scan", "scan"):
        hints.append(
            'SimpleSecCheck: `service_key` **`ssc_api_key`** — API-Key aus https://scan.fr4iser.com → API Keys (`ssc_…`). '
            "Operator alternativ: `SSC_API_KEY` und optional `SSC_BASE_URL` in docker/.env."
        )
    if topic in ("calendar", "ics", "caldav", "nextcloud"):
        hints.append(
            'Kalender read-only: **`calendar_ics`** oder **`google_calendar`** (gleiches JSON `{"ics_url":"https://…"}`). '
            "Google: Kalendereinstellungen → *Geheime Adresse im iCal-Format*. Es reicht **ein** gespeicherter Key — der Agent probiert `google_calendar` zuerst."
        )
    if topic in ("google", "gcal", "google_calendar"):
        hints.append(
            'Google Kalender: `register_secrets` mit `service_key_example: "google_calendar"`; Secret = iCal-URL aus den Google-Kalendereinstellungen.'
        )

    return json.dumps(
        {
            "ok": True,
            "otp_only_from_register_secrets_de": (
                "Ein **OTP** und der fertige **`curl_bash`** kommen **ausschließlich** aus der Tool-Antwort von "
                "`register_secrets`. **`secrets_help` ruft das Backend nicht an** und erzeugt **kein** OTP."
            ),
            "when_backend_emits_otp_de": (
                "Wenn dein Modell keine nativen ``tool_calls`` sendet, wird ``register_secrets`` nicht ausgeführt → **kein** OTP. "
                "Ein Modell/Build mit zuverlässigem Tool-Calling wählen. Nur in Ausnahmefällen ``AGENT_CONTENT_TOOL_FALLBACK=true`` "
                "(liest Tool-Intent aus dem Assistant-Text; Standard ist **false**)."
            ),
            "gmail_save_use_this_tool": "register_secrets",
            "gmail_save_example_args": {"service_key_example": "gmail"},
            "google_calendar_save_example_args": {
                "service_key_example": "google_calendar"
            },
            "service_key_example": raw_svc,
            "base_url_used": base,
            "auth_identity": auth_identity,
            "resolved_user_id": uid,
            "resolved_external_sub": user_value,
            "for_llm_de": (
                "Neues Secret speichern: **Web-UI** Einstellungen → Connections (Formulare), **oder** `register_secrets` "
                "mit passendem `service_key_example` (gmail, google_calendar, calendar_ics, github_pat, …). "
                "Bei curl: Dem Nutzer **nur** `curl_bash` / `jq_register_example_de` aus **dieser** Antwort geben — nichts erfinden. "
                "Klartext-Secrets und iCal-URLs **nie** in den Chat."
            ),
            "common_mistakes_de": [
                "Falsch: `secrets_help` aufrufen und erwarten, dass ein OTP oder curl erscheint.",
                "Falsch: Geheime iCal-URL oder Passwörter in den Chat schreiben — nur lokal im Terminal im curl/jq.",
            ],
            "preferred_flow_de": (
                "`register_secrets` → Nutzer führt `curl_bash` (eine Zeile) lokal aus → HTTP-Antwort `stored:true`. "
                "Danach z. B. `calendar_ics_list_events` für Google-Kalender."
            ),
            "steps_de": [
                "Tool `register_secrets` mit JSON-Argumenten aufrufen, z. B. "
                '`{"service_key_example":"google_calendar"}` oder `{"service_key_example":"gmail"}`.',
                "Aus der **Tool-Antwort** `curl_bash` oder `jq_register_example_de` kopieren, Platzhalter lokal ersetzen, ausführen.",
                "Bei Google-Kalender: in `secret` die komplette https-URL (`…/basic.ics`) einsetzen (nur im Terminal).",
            ],
            "list_delete_note_de": (
                "Gespeicherte Keys auflisten oder löschen: REST `GET` bzw. `DELETE /v1/user/secrets` "
            ),
            "hints": hints,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "secrets_help": secrets_help,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "secrets_help",
            "TOOL_DESCRIPTION": (
                "Static help for user secrets: explains that OTP and curl_bash come ONLY from register_secrets — "
                "this tool does NOT mint an OTP. To save Gmail, google_calendar, github_pat, etc., the model must "
                "call register_secrets and pass the returned curl_bash to the user. "
                "Returns steps_de, google_calendar_save_example_args, list_delete_note_de (REST for list/delete), hints."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key_example": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Example service_key name for hints only (lowercase [a-z0-9._-]), "
                            "e.g. gmail, google_calendar, github_pat"
                        ),
                    },
                    "topic": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional hint: email, imap, mail, gmail, github, google, gcal, calendar, ics, or generic"
                        ),
                    },
                },
            },
        },
    },
]