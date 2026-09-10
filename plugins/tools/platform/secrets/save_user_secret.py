"""Chat tool: store a per-user encrypted secret directly (no OTP curl)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.infrastructure.platform.config import config
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.secret_otp_bundle import validate_user_secret_service_key
from plugins.tools.workspace.lib.common import workspace_id_from_context

__version__ = "1.1.0"
TOOL_ID = "save_user_secret"
TOOL_BUCKET = "secrets"
TOOL_DOMAIN = "secrets"
TOOL_LABEL = "Secrets"
TOOL_DESCRIPTION = (
    "Store an encrypted credential for the signed-in chat user. "
    "scope=workspace (default when a project workspace is bound and the key is not a "
    "catalog integration key) stores under this workspace so projects can share env names "
    "with different values. scope=global stores account-wide (github_pat, ssc_api_key, …). "
    "service_key: lowercase [a-z0-9._-] — catalog key or FOO_BAR → foo_bar. "
    "When a workspace is bound, non-catalog keys auto-create env_bindings "
    "(FOO_BAR ← foo_bar) so bash injects them — no separate env_bindings call needed. "
    "Never echo the secret value back. Never write .env files."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("secrets.user",)


def _catalog_service_keys() -> list[str]:
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


def _parse_workspace_id(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _resolve_scope(
    arguments: dict[str, Any],
    *,
    service_key: str,
    bound_workspace_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID | None]:
    """Return (scope, workspace_id) with defaults."""
    catalog = set(_catalog_service_keys())
    raw_scope = str(arguments.get("scope") or "").strip().lower()
    arg_wid = _parse_workspace_id(arguments.get("workspace_id"))
    wid = arg_wid or bound_workspace_id

    if raw_scope in ("global", "user"):
        return "global", None
    if raw_scope in ("workspace", "project"):
        return "workspace", wid
    # Default: catalog → global; otherwise workspace when bound.
    if service_key in catalog:
        return "global", None
    if wid is not None:
        return "workspace", wid
    return "global", None


def save_user_secret(arguments: dict[str, Any], context: dict | None = None) -> str:
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
                    "Prefer a catalog key when an integration declares one. "
                    "For project env vars, derive service_key by lowercasing the env name "
                    "(FOO_BAR → foo_bar); env_bindings are created automatically when a "
                    "workspace is bound."
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

    bound_wid = _parse_workspace_id(workspace_id_from_context(context))
    scope, wid = _resolve_scope(arguments, service_key=sk, bound_workspace_id=bound_wid)
    explicit_env = str(arguments.get("env_name") or "").strip() or None

    try:
        if scope == "workspace":
            if wid is None:
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            "scope=workspace requires a bound project workspace "
                            "(or pass workspace_id)"
                        ),
                    },
                    ensure_ascii=False,
                )
            db.user_workspace_secret_upsert(uid, wid, sk, secret)
        else:
            db.user_secret_upsert(uid, sk, secret)
    except RuntimeError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    payload: dict[str, Any] = {
        "ok": True,
        "stored": True,
        "service_key": sk,
        "scope": scope,
        "for_assistant_must_say_de": (
            "Secret wurde gespeichert. Den Klartext **nicht** wiederholen oder zitieren."
        ),
    }
    if scope == "workspace" and wid is not None:
        payload["workspace_id"] = str(wid)

    # Auto-bind so Coding/bash injects without a separate env_bindings step.
    bind_wid = wid if scope == "workspace" else bound_wid
    catalog = set(_catalog_service_keys())
    should_bind = bind_wid is not None and (sk not in catalog or explicit_env)
    if should_bind:
        from plugins.tools.workspace.lib.env_secret_bridge import ensure_env_binding_for_secret

        bind_info = ensure_env_binding_for_secret(
            user_id=uid,
            workspace_id=bind_wid,
            service_key=sk,
            env_name=explicit_env,
        )
        payload["env_binding"] = bind_info
        if bind_info.get("bound"):
            payload["for_assistant_must_say_de"] = (
                "Secret gespeichert und für bash gebunden "
                f"({bind_info.get('env')} ← {sk}). Klartext nicht wiederholen — "
                "direkt Coding/bash fortsetzen."
            )
    return json.dumps(payload, ensure_ascii=False)


HANDLERS: dict[str, Callable[..., str]] = {
    "save_user_secret": save_user_secret,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_user_secret",
            "chat_full_parameters": True,
            "TOOL_DESCRIPTION": (
                "Store a user secret immediately (no OTP curl). "
                "scope=workspace (default for non-catalog keys when a workspace is bound) "
                "or scope=global. Auto-creates env_bindings for bash when a workspace is bound. "
                "Required: service_key + secret. Never echo the secret."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Secret slot name (lowercase [a-z0-9._-]). Prefer catalog keys "
                            "(e.g. ssc_api_key). For project env vars, lowercase the env name "
                            "(FOO_BAR → foo_bar)."
                        ),
                    },
                    "secret": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Credential to store (plain string or JSON object as string)."
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "global = account-wide; workspace = this project only "
                            "(avoids env-name clashes across projects). Default: workspace "
                            "when bound and key is not a catalog integration key."
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional workspace UUID for scope=workspace "
                            "(defaults to the currently bound workspace)."
                        ),
                    },
                    "env_name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional process env name for auto-binding (default: uppercased "
                            "service_key, e.g. foo_bar → FOO_BAR)."
                        ),
                    },
                },
                "required": ["service_key", "secret"],
            },
        },
    },
]
