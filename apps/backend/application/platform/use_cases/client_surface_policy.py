"""Application façade for client surface / API-key workspace policy (ADR 0009)."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.platform.client_surface_policy import (
    apply_surface_preset as _apply_surface_preset,
    is_browser_chat_path as _is_browser_chat_path,
    public_policy as _public_policy,
    refuse_api_key_auth as _refuse_api_key_auth,
    refuse_api_key_mint as _refuse_api_key_mint,
    refuse_api_key_workspace_mode as _refuse_api_key_workspace_mode,
    request_uses_api_key as _request_uses_api_key,
    surface_preset as _surface_preset,
    web_ui_enabled as _web_ui_enabled,
)


def public_policy() -> dict[str, Any]:
    return _public_policy()


def surface_preset() -> str:
    return _surface_preset()


def apply_surface_preset(preset: str) -> dict[str, Any]:
    return _apply_surface_preset(preset)


def web_ui_enabled() -> bool:
    return _web_ui_enabled()


def is_browser_chat_path(path: str) -> bool:
    return _is_browser_chat_path(path)


def refuse_web_ui_path(path: str) -> str | None:
    if web_ui_enabled() or not is_browser_chat_path(path):
        return None
    return (
        "Web UI chat and dashboards are disabled by the operator (TUI_ONLY). "
        "Use login/admin, or ask an admin to enable web_ui_enabled / set surface_preset WEB_AND_TUI."
    )


def refuse_api_key_auth() -> str | None:
    return _refuse_api_key_auth()


def refuse_api_key_mint() -> str | None:
    return _refuse_api_key_mint()


def refuse_api_key_workspace_mode(execution_mode: Any) -> str | None:
    return _refuse_api_key_workspace_mode(execution_mode)


def refuse_server_workspace_for_user(user: Any, execution_mode: Any) -> str | None:
    from apps.backend.infrastructure.platform.client_surface_policy import (
        refuse_server_workspace_for_user as _refuse,
    )

    return _refuse(user, execution_mode)


def server_workspaces_admin_only() -> bool:
    from apps.backend.infrastructure.platform.client_surface_policy import (
        server_workspaces_admin_only as _flag,
    )

    return _flag()


def user_may_use_server_workspaces(user: Any) -> bool:
    from apps.backend.infrastructure.platform.client_surface_policy import (
        user_may_use_server_workspaces as _may,
    )

    return _may(user)


def request_uses_api_key() -> bool:
    return _request_uses_api_key()
