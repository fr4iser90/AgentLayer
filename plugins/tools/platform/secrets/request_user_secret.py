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
from plugins.tools.workspace.lib.common import workspace_id_from_context

__version__ = "1.2.0"
TOOL_ID = "request_user_secret"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Request user secret (UI)"
TOOL_DESCRIPTION = (
    "Show an in-chat form so the signed-in user can save a credential (Web UI). "
    "service_key: catalog keys when declared (e.g. github_pat), otherwise derive from "
    "the env/var name (FOO_BAR → foo_bar). For project env vars with a bound workspace, "
    "defaults to workspace scope (same env names, different values per project). "
    "Any signed-in user can save their own secrets — admin role is not required."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("secrets.user",)


def request_user_secret(arguments: dict[str, Any], context: dict | None = None) -> str:
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
    raw_scope = str(arguments.get("scope") or "").strip().lower()
    arg_wid = str(arguments.get("workspace_id") or "").strip() or None
    bound_wid = workspace_id_from_context(context)
    wid = arg_wid or bound_wid

    if raw_scope in ("global", "user"):
        scope = "global"
        wid = None
    elif raw_scope in ("workspace", "project"):
        scope = "workspace"
    elif in_catalog or not wid:
        scope = "global"
        wid = None
    else:
        scope = "workspace"

    if scope == "workspace" and not wid:
        return json.dumps(
            {
                "ok": False,
                "error": "scope=workspace requires a bound workspace (or workspace_id)",
            },
            ensure_ascii=False,
        )

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
                + (" (workspace-scoped)." if scope == "workspace" else ".")
            )
    prompt_id = str(uuid.uuid4())
    secret_prompt: dict[str, Any] = {
        "prompt_id": prompt_id,
        "service_key": sk,
        "mode": "authenticated",
        "scope": scope,
        "title": title,
        "help": help_text,
        "fields": fields,
        "reason": reason or None,
    }
    if scope == "workspace" and wid:
        secret_prompt["workspace_id"] = str(wid)
    return json.dumps(
        {
            "ok": True,
            "ui_emitted": True,
            "prompt_id": prompt_id,
            "service_key": sk,
            "scope": scope,
            "workspace_id": str(wid) if scope == "workspace" and wid else None,
            "catalog_key": in_catalog,
            "secret_prompt": secret_prompt,
            "for_assistant_must_say_de": (
                "Eine Eingabe-Card erscheint im Chat — der Nutzer trägt das Secret ein und klickt Speichern. "
                "Kein curl. Secret nicht wiederholen. Nach Speichern (workspace): env_bindings "
                "entstehen automatisch — direkt Coding/bash fortsetzen. Admin-Rolle ist nicht nötig."
            ),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "request_user_secret": request_user_secret,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "request_user_secret",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": (
                "Show the in-chat secret registration card (Web UI). "
                "Optional scope=workspace|global and workspace_id. "
                "service_key: catalog key or lowercased env name."
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
                    "scope": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "global | workspace (default: workspace when bound).",
                    },
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional workspace UUID for scope=workspace.",
                    },
                },
                "required": ["service_key"],
            },
        },
    },
]
