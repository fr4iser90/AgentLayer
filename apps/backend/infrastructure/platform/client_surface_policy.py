"""Operator policy for which clients may connect, and what API-key clients may do.

Presets (derived, not stored):
  WEB_ONLY     — web on, API keys off
  WEB_AND_TUI  — both on (default)
  TUI_ONLY     — web chat off, API keys on (login/admin SPA still served)

``api_key_workspace_modes`` limits ``execution_mode`` create/bind for API-key
auth only. ``workspace_index_consent_max`` (separate module) still caps indexing.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any, Literal

logger = logging.getLogger(__name__)

AuthMaterial = Literal["none", "jwt", "api_key"]
WorkspaceModes = Literal["server", "client", "both"]
SurfacePreset = Literal["WEB_ONLY", "WEB_AND_TUI", "TUI_ONLY"]

_AUTH_MATERIAL: ContextVar[AuthMaterial] = ContextVar("client_auth_material", default="none")

_CACHE: tuple[float, dict[str, Any]] | None = None
_TTL_SEC = 2.0

_VALID_MODES = frozenset({"server", "client", "both"})


def set_auth_material(kind: AuthMaterial) -> None:
    _AUTH_MATERIAL.set(kind)


def reset_auth_material() -> None:
    _AUTH_MATERIAL.set("none")


def current_auth_material() -> AuthMaterial:
    return _AUTH_MATERIAL.get()


def request_uses_api_key() -> bool:
    return current_auth_material() == "api_key"


def invalidate_client_surface_cache() -> None:
    global _CACHE
    _CACHE = None


def _defaults() -> dict[str, Any]:
    return {
        "web_ui_enabled": True,
        "api_key_clients_enabled": True,
        "api_key_workspace_modes": "both",
        "server_workspaces_admin_only": True,
    }


def _read_row() -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if _CACHE is not None and now - _CACHE[0] < _TTL_SEC:
        return dict(_CACHE[1])
    out = _defaults()
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT web_ui_enabled, api_key_clients_enabled, api_key_workspace_modes,
                           server_workspaces_admin_only
                      FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
            conn.commit()
        if row:
            out["web_ui_enabled"] = bool(row[0]) if row[0] is not None else True
            out["api_key_clients_enabled"] = bool(row[1]) if row[1] is not None else True
            mode = str(row[2] or "both").strip().lower()
            out["api_key_workspace_modes"] = mode if mode in _VALID_MODES else "both"
            if len(row) > 3 and row[3] is not None:
                out["server_workspaces_admin_only"] = bool(row[3])
    except Exception as exc:
        logger.debug("client_surface_policy read: %s", exc)
    _CACHE = (now, dict(out))
    return out


def web_ui_enabled() -> bool:
    return bool(_read_row()["web_ui_enabled"])


def api_key_clients_enabled() -> bool:
    return bool(_read_row()["api_key_clients_enabled"])


def api_key_workspace_modes() -> WorkspaceModes:
    mode = str(_read_row()["api_key_workspace_modes"] or "both").strip().lower()
    return mode if mode in _VALID_MODES else "both"  # type: ignore[return-value]


def server_workspaces_admin_only() -> bool:
    return bool(_read_row().get("server_workspaces_admin_only", True))


def user_may_use_server_workspaces(user: Any) -> bool:
    """Admins always may; when the operator flag is off, everyone may."""
    if not server_workspaces_admin_only():
        return True
    role = str(getattr(user, "role", None) or "").strip().lower()
    if role == "admin":
        return True
    uid = getattr(user, "id", None)
    if uid is not None:
        try:
            from apps.backend.infrastructure.db import db

            if db.user_role(uid) == "admin":
                return True
            if db.user_site_role(uid) == "site_admin":
                return True
        except Exception:
            pass
    return False


def refuse_server_workspace_for_user(user: Any, execution_mode: Any) -> str | None:
    """Refuse create/bind/use of server workspaces for non-admins when policy is on."""
    from apps.backend.infrastructure.workspace.workspace_columns import (
        CLIENT_EXECUTION,
        normalize_execution_mode,
    )

    if normalize_execution_mode(execution_mode) == CLIENT_EXECUTION:
        return None
    if user_may_use_server_workspaces(user):
        return None
    return (
        "Server (hosted) workspaces are restricted to admins. "
        "Create or bind a client workspace (execution_mode=client) on your machine, "
        "or ask an admin to disable server_workspaces_admin_only."
    )


def normalize_workspace_modes(raw: Any) -> WorkspaceModes | None:
    v = str(raw or "").strip().lower()
    return v if v in _VALID_MODES else None  # type: ignore[return-value]


def surface_preset() -> SurfacePreset:
    web = web_ui_enabled()
    keys = api_key_clients_enabled()
    if web and not keys:
        return "WEB_ONLY"
    if keys and not web:
        return "TUI_ONLY"
    return "WEB_AND_TUI"


def apply_surface_preset(preset: str) -> dict[str, Any]:
    """Map a preset name to column values (does not write the DB)."""
    p = str(preset or "").strip().upper().replace("-", "_").replace(" ", "_")
    if p in ("WEB_ONLY", "WEBONLY", "WEB"):
        return {
            "web_ui_enabled": True,
            "api_key_clients_enabled": False,
            "api_key_workspace_modes": api_key_workspace_modes(),
        }
    if p in ("TUI_ONLY", "TUIONLY", "TUI", "CLIENT_ONLY"):
        return {
            "web_ui_enabled": False,
            "api_key_clients_enabled": True,
            "api_key_workspace_modes": api_key_workspace_modes(),
        }
    if p in ("WEB_AND_TUI", "BOTH", "ALL", "WEB_TUI"):
        return {
            "web_ui_enabled": True,
            "api_key_clients_enabled": True,
            "api_key_workspace_modes": api_key_workspace_modes(),
        }
    raise ValueError("surface_preset must be WEB_ONLY, WEB_AND_TUI, or TUI_ONLY")


def public_policy() -> dict[str, Any]:
    from apps.backend.infrastructure.workspace.workspace_index_consent import operator_index_consent_max

    modes = api_key_workspace_modes()
    return {
        "web_ui_enabled": web_ui_enabled(),
        "api_key_clients_enabled": api_key_clients_enabled(),
        "api_key_workspace_modes": modes,
        "surface_preset": surface_preset(),
        "workspace_index_consent_max": operator_index_consent_max(),
        "api_key_may_use_server_workspaces": modes in ("server", "both"),
        "api_key_may_use_client_workspaces": modes in ("client", "both"),
        "server_workspaces_admin_only": server_workspaces_admin_only(),
    }


def refuse_api_key_auth() -> str | None:
    if api_key_clients_enabled():
        return None
    return (
        "API-key clients are disabled by the operator (WEB_ONLY). "
        "Use the Web UI session, or ask an admin to enable api_key_clients_enabled."
    )


def refuse_api_key_mint() -> str | None:
    return refuse_api_key_auth()


def mode_allowed_for_api_key(execution_mode: Any) -> bool:
    from apps.backend.infrastructure.workspace.workspace_columns import (
        CLIENT_EXECUTION,
        normalize_execution_mode,
    )

    modes = api_key_workspace_modes()
    mode = normalize_execution_mode(execution_mode)
    if modes == "both":
        return True
    if modes == "client":
        return mode == CLIENT_EXECUTION
    return mode != CLIENT_EXECUTION


def refuse_api_key_workspace_mode(execution_mode: Any) -> str | None:
    if not request_uses_api_key():
        return None
    if mode_allowed_for_api_key(execution_mode):
        return None
    modes = api_key_workspace_modes()
    return (
        f"API-key clients may only use execution_mode allowed by the operator "
        f"(api_key_workspace_modes={modes}). Requested: {execution_mode!r}."
    )


def is_browser_chat_path(path: str) -> bool:
    """Paths that are user Web UI (not login/setup/admin escape hatches)."""
    p = (path or "").rstrip("/") or "/"
    if p in ("/app", "/app/"):
        return True
    blocked_prefixes = (
        "/app/chat",
        "/app/dashboard",
        "/app/docs",
        "/app/schedules",
        "/app/tasks",
        "/app/projects",
        "/app/studio",
        "/app/settings",
        "/app/org",
        "/coding-agent",
        "/chat",
        "/dashboard",
    )
    return any(p == pref or p.startswith(pref + "/") for pref in blocked_prefixes)
