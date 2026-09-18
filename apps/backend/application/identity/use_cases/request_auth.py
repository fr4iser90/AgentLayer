from __future__ import annotations

from typing import Any

from fastapi import Request

from apps.backend.infrastructure.identity.auth import (
    LoginRequest,
    User,
    bearer_is_interactive_session as _bearer_is_interactive_session,
    create_access_token as _create_access_token,
    create_api_key as _create_api_key,
    create_refresh_token as _create_refresh_token,
    create_user as _create_user,
    get_current_user as _get_current_user,
    get_user_by_email as _get_user_by_email,
    get_user_by_id as _get_user_by_id,
    get_user_for_bearer_token as _get_user_for_bearer_token,
    hash_refresh_token as _hash_refresh_token,
    list_all_users as _list_all_users,
    list_api_keys as _list_api_keys,
    require_admin as _require_admin,
    require_site_admin as _require_site_admin,
    require_admin_capability as _require_admin_capability,
    require_admin_scope as _require_admin_scope,
    require_tenant_admin as _require_tenant_admin,
    require_tenant_member as _require_tenant_member,
    require_permission as _require_permission,
    revoke_api_key as _revoke_api_key,
    revoke_refresh_token as _revoke_refresh_token,
    update_user_password as _update_user_password,
    update_user_tenant as _update_user_tenant,
    validate_refresh_token as _validate_refresh_token,
    verify_password as _verify_password,
)


async def get_current_user(request: Request) -> Any:
    return await _get_current_user(request)


async def require_admin(request: Request) -> Any:
    return await _require_admin(request)


async def require_site_admin(request: Request) -> Any:
    return await _require_site_admin(request)


async def require_admin_capability(request: Request, capability: str) -> Any:
    return await _require_admin_capability(request, capability)


async def require_admin_scope(request: Request, capability: str) -> Any:
    """Capability gate plus the tenant range the action may reach.

    Handlers that create, move or grant against a *target* must use this rather
    than :func:`require_admin_capability` — the capability says what, the scope
    says where.
    """
    return await _require_admin_scope(request, capability)


def agent_effective_role(user_id: Any, fallback_role: str | None = None) -> str:
    """Agent/admin elevation resolved from the canonical ``users.site_role``.

    Mirrors ``chat_run_bootstrap``: a legacy ``users.role='admin'`` paired with
    ``site_role='site_user'`` must **not** elevate. ``fallback_role`` is used only
    when the ``site_role`` lookup is unavailable.

    Callers that feed a role into ``user_may_invoke_agent`` /
    ``schedule_permission_error`` should pass this instead of ``db.user_role()``,
    otherwise the pre-P1 privilege-escalation path reopens on that surface.
    """
    from apps.backend.infrastructure.db import db

    site_flag: bool | None = None
    if user_id is not None:
        try:
            site_flag = db.user_site_admin(user_id)
        except Exception:
            site_flag = None
    if site_flag is not None:
        return "admin" if site_flag else "user"
    return (str(fallback_role or "user").strip().lower()) or "user"


async def require_tenant_admin(request: Request) -> Any:
    return await _require_tenant_admin(request)


async def require_tenant_member(request: Request) -> Any:
    return await _require_tenant_member(request)


def get_user_by_id(user_id: Any) -> Any:
    return _get_user_by_id(user_id)


def get_user_by_email(email: str) -> Any:
    return _get_user_by_email(email)


def get_user_for_bearer_token(token: str) -> Any:
    return _get_user_for_bearer_token(token)


def require_permission(action: str, resource_type: str | None = None) -> Any:
    return _require_permission(action, resource_type)


def verify_password(password: str, password_hash: str) -> bool:
    return _verify_password(password, password_hash)


def create_access_token(user_id: Any, role: str) -> str:
    return _create_access_token(user_id, role)


def create_refresh_token(user_id: Any) -> tuple[str, str]:
    return _create_refresh_token(user_id)


def hash_refresh_token(token: str) -> str:
    return _hash_refresh_token(token)


def validate_refresh_token(token: str) -> Any:
    return _validate_refresh_token(token)


def revoke_refresh_token(token: str) -> bool:
    return _revoke_refresh_token(token)


def list_all_users(tenant_ids: frozenset[int] | None = None) -> list[dict[str, Any]]:
    return _list_all_users(tenant_ids)


def create_user(email: str, password: str, role: str = "user", tenant_id: int = 1) -> Any:
    return _create_user(email, password, role, tenant_id)


def update_user_tenant(user_id: Any, tenant_id: int) -> bool:
    return _update_user_tenant(user_id, tenant_id)


def update_user_password(user_id: Any, password: str) -> None:
    _update_user_password(user_id, password)


def bearer_is_interactive_session(token: str) -> bool:
    return _bearer_is_interactive_session(token)


def create_api_key(user_id: Any, name: str, expires_at: Any = None) -> tuple[str, dict[str, Any]]:
    return _create_api_key(user_id, name, expires_at)


def list_api_keys(user_id: Any) -> list[dict[str, Any]]:
    return _list_api_keys(user_id)


def revoke_api_key(user_id: Any, key_id: Any) -> bool:
    return _revoke_api_key(user_id, key_id)
