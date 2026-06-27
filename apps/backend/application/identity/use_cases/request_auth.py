from __future__ import annotations

from typing import Any

from fastapi import Request

from apps.backend.infrastructure.identity.auth import (
    LoginRequest,
    User,
    create_access_token as _create_access_token,
    create_refresh_token as _create_refresh_token,
    create_user as _create_user,
    get_current_user as _get_current_user,
    get_user_by_email as _get_user_by_email,
    get_user_by_id as _get_user_by_id,
    get_user_for_bearer_token as _get_user_for_bearer_token,
    hash_refresh_token as _hash_refresh_token,
    list_all_users as _list_all_users,
    require_admin as _require_admin,
    require_permission as _require_permission,
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


def list_all_users() -> list[dict[str, Any]]:
    return _list_all_users()


def create_user(email: str, password: str, role: str = "user", tenant_id: int = 1) -> Any:
    return _create_user(email, password, role, tenant_id)


def update_user_tenant(user_id: Any, tenant_id: int) -> bool:
    return _update_user_tenant(user_id, tenant_id)


def update_user_password(user_id: Any, password: str) -> None:
    _update_user_password(user_id, password)
