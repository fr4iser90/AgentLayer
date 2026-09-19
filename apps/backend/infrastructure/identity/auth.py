"""
Authentication & Authorization Layer for Agent Layer
JWT Access + Refresh Tokens, BCrypt Password Hashing, Permission System
"""
from __future__ import annotations

import hashlib
import os
import bcrypt
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import TYPE_CHECKING, Optional, Callable, Any

from fastapi import Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.api_keys import (
    API_KEY_PREFIX,
    create_api_key,
    generate_api_key,
    hash_api_key,
    list_api_keys,
    revoke_api_key,
)
from apps.backend.domain.shared.identity import set_identity, reset_identity
from apps.backend.infrastructure.dashboards.dashboard_persistence import ensure_default_dashboard_for_new_user
from apps.backend.infrastructure.access.tenant_entity_transfer import guarded_move_user_tenant

if TYPE_CHECKING:
    from apps.backend.domain.access.capabilities import AdminScope


# JWT Configuration
JWT_SECRET = os.environ.get("AGENT_JWT_SECRET", os.urandom(32).hex())
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    password_hash: str | None = Field(default=None, exclude=True)


class LoginRequest(BaseModel):
    email: str
    password: str


def hash_password(password: str) -> str:
    """Hash password with bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash"""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Create short-lived JWT access token"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def hash_refresh_token(token: str) -> str:
    """Fixed-length digest for indexed DB lookup (not bcrypt — refresh tokens are high-entropy)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Create long-lived refresh token, returns (token, token_hash)."""
    token = uuid.uuid4().hex
    return token, hash_refresh_token(token)


def validate_refresh_token(token: str) -> Optional[User]:
    """Validate refresh token and return user if valid."""
    raw = (token or "").strip()
    if not raw:
        return None
    digest = hash_refresh_token(raw)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id FROM refresh_tokens
                WHERE token_hash = %s AND expires_at > NOW()
                LIMIT 1
                """,
                (digest,),
            )
            row = cur.fetchone()
            if row:
                return get_user_by_id(row[0])
            # Legacy rows (bcrypt) until users re-login; avoid full-table scan on modern tokens.
            cur.execute(
                """
                SELECT user_id, token_hash
                FROM refresh_tokens
                WHERE expires_at > NOW() AND token_hash LIKE '$2%%'
                """
            )
            for user_id, token_hash in cur.fetchall():
                if verify_password(raw, token_hash):
                    return get_user_by_id(user_id)
    return None


def revoke_refresh_token(token: str) -> bool:
    """Delete refresh session matching the raw token (e.g. on logout). Returns True if a row was removed."""
    raw = (token or "").strip()
    if not raw:
        return False
    digest = hash_refresh_token(raw)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM refresh_tokens
                WHERE token_hash = %s AND expires_at > NOW()
                RETURNING id
                """,
                (digest,),
            )
            if cur.fetchone():
                conn.commit()
                return True
            cur.execute(
                """
                SELECT id, token_hash
                FROM refresh_tokens
                WHERE expires_at > NOW() AND token_hash LIKE '$2%%'
                """
            )
            for rid, token_hash in cur.fetchall():
                if verify_password(raw, token_hash):
                    cur.execute("DELETE FROM refresh_tokens WHERE id = %s", (rid,))
                    conn.commit()
                    return True
    return False


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT access token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email"""
    # tenant-scope: site-wide — login happens before a tenant is known, and
    # users_email_key is unique across the instance.
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, role, created_at, password_hash
                FROM users
                WHERE email = %s
            """, (email,))
            row = cur.fetchone()
            if not row:
                return None
            return User(
                id=row[0],
                email=row[1],
                role=row[2],
                created_at=row[3],
                password_hash=row[4],
            )


def _normalize_capabilities(raw: Any) -> list[str]:
    """Normalize a JSONB capabilities value to a sorted list of lowercase slugs."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip().lower() for x in raw if str(x).strip()]
        return sorted(set(items))
    return []


def list_all_users(tenant_ids: frozenset[int] | None = None) -> list[dict[str, Any]]:
    """
    All ``users`` rows for admin UI. ``email`` is nullable in the schema; do not build ``User``
    here or Pydantic rejects NULL emails.

    ``tenant_ids=None`` means every tenant — pass it only for a site admin. A
    delegated ``user.manage`` holder must pass their :meth:`AdminScope.tenant_filter`
    result so the People list cannot read mailboxes across companies.
    """
    where = ""
    params: tuple[Any, ...] = ()
    if tenant_ids is not None:
        if not tenant_ids:
            return []
        placeholders = ", ".join(["%s"] * len(tenant_ids))
        where = f"WHERE u.tenant_id IN ({placeholders}) "
        params = tuple(sorted(tenant_ids))

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT u.id, u.email, u.role, u.site_role, u.created_at, u.external_sub, u.display_name,
                       u.tenant_id, t.name AS tenant_name, u.discord_user_id, u.telegram_user_id,
                       COALESCE(u.workspace_quota, 10) AS workspace_quota,
                       COALESCE(u.workspace_self_allowed, false) AS workspace_self_allowed,
                       COALESCE(u.schedules_allowed, false) AS schedules_allowed,
                       COALESCE(u.dashboards_allowed, true) AS dashboards_allowed,
                       COALESCE(u.dashboard_quota, 1) AS dashboard_quota,
                       u.media_storage_quota_mb,
                       u.media_enabled,
                       u.media_upload_enabled,
                       u.llm_queue_priority,
                       COALESCE(u.capabilities, '[]'::jsonb) AS capabilities
                FROM users u
                LEFT JOIN tenants t ON t.id = u.tenant_id
                {where}ORDER BY u.created_at ASC NULLS LAST, u.email ASC NULLS LAST, u.external_sub ASC
                """,
                params,
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        (
            uid,
            email,
            role,
            site_role,
            created_at,
            external_sub,
            display_name,
            tenant_id,
            tenant_name,
            discord_uid,
            telegram_uid,
            workspace_quota,
            workspace_self_allowed,
            schedules_allowed,
            dashboards_allowed,
            dashboard_quota,
            media_storage_quota_mb,
            media_enabled,
            media_upload_enabled,
            llm_queue_priority,
            capabilities,
        ) = row
        tid = int(tenant_id) if tenant_id is not None else 1
        du = str(discord_uid).strip() if discord_uid is not None else ""
        tu = str(telegram_uid).strip() if telegram_uid is not None else ""
        out.append(
            {
                "id": str(uid),
                "email": email or "",
                "role": role,
                "site_role": site_role,
                "created_at": created_at.isoformat() if created_at else "",
                "external_sub": external_sub,
                "display_name": display_name,
                "tenant_id": tid,
                "tenant_name": (tenant_name or "") if tenant_name is not None else "",
                "discord_user_id": du or None,
                "telegram_user_id": tu or None,
                "workspace_quota": workspace_quota if workspace_quota is not None else 10,
                "workspace_self_allowed": bool(workspace_self_allowed) if workspace_self_allowed is not None else False,
                "schedules_allowed": bool(schedules_allowed) if schedules_allowed is not None else False,
                "dashboards_allowed": bool(dashboards_allowed) if dashboards_allowed is not None else True,
                "dashboard_quota": int(dashboard_quota) if dashboard_quota is not None else 1,
                "media_storage_quota_mb": int(media_storage_quota_mb)
                if media_storage_quota_mb is not None
                else None,
                "media_enabled": media_enabled if media_enabled is not None else None,
                "media_upload_enabled": media_upload_enabled if media_upload_enabled is not None else None,
                "llm_queue_priority": int(llm_queue_priority)
                if llm_queue_priority is not None
                else None,
                "capabilities": _normalize_capabilities(capabilities),
            }
        )
    return out


def get_user_by_id(user_id: uuid.UUID) -> Optional[User]:
    """Get user by id"""
    # tenant-scope: site-wide — canonical identity lookup; callers decide what
    # the user's tenant permits.
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, role, created_at
                FROM users
                WHERE id = %s
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return User(
                id=row[0],
                email=row[1],
                role=row[2],
                created_at=row[3],
            )


async def get_current_user(request: Request) -> User:
    """
    Middleware to resolve current user from request
    Supports:
    - Bearer JWT Token
    - Bearer API Key
    - Legacy global API Key (fallback for backwards compatibility)
    """

    # Check for authorization header
    auth = request.headers.get("authorization") or ""
    token = auth.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = get_user_for_bearer_token(token)
    if user:
        return user

    if not decode_access_token(token) and token.startswith(API_KEY_PREFIX):
        from apps.backend.infrastructure.platform.client_surface_policy import refuse_api_key_auth

        refuse = refuse_api_key_auth()
        if refuse:
            raise HTTPException(status_code=403, detail=refuse)

    raise HTTPException(status_code=401, detail="Unauthorized")


def bearer_is_interactive_session(token: str) -> bool:
    """
    True for a JWT access token, False for an API key.

    Key management is gated on this so a leaked key cannot mint a replacement that outlives
    its own revocation.
    """
    return bool(decode_access_token((token or "").strip()))


def get_user_for_bearer_token(token: str) -> Optional[User]:
    """
    Resolve user from JWT access token or API key string (same rules as ``Authorization: Bearer``).
    For WebSockets where headers/query carry the token without a full ``Request`` cycle.
    """
    from apps.backend.infrastructure.platform.client_surface_policy import (
        refuse_api_key_auth,
        reset_auth_material,
        set_auth_material,
    )

    raw = (token or "").strip()
    if not raw:
        reset_auth_material()
        return None
    payload = decode_access_token(raw)
    if payload and payload.get("sub"):
        try:
            user = get_user_by_id(uuid.UUID(str(payload["sub"])))
            if user:
                set_auth_material("jwt")
                return user
        except (ValueError, TypeError):
            pass
    if refuse_api_key_auth():
        reset_auth_material()
        return None
    digest = hash_api_key(raw)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id FROM api_keys
                WHERE key_hash = %s
                  AND (expires_at IS NULL OR expires_at > NOW())
                """,
                (digest,),
            )
            row = cur.fetchone()
            if row:
                user = get_user_by_id(row[0])
                if user:
                    cur.execute(
                        "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = %s",
                        (digest,),
                    )
                    conn.commit()
                    set_auth_material("api_key")
                    return user
    reset_auth_material()
    return None


async def require_admin(request: Request) -> User:
    """Site admin (platform operator). Alias for require_site_admin."""
    return await require_site_admin(request)


async def require_site_admin(request: Request) -> User:
    user = await get_current_user(request)
    if db.user_site_role(user.id) != "site_admin":
        raise HTTPException(status_code=403, detail="site admin required")
    return user


async def require_admin_capability(request: Request, capability: str) -> User:
    """Require a platform/admin capability (P6, Weg B). Site admin holds all.

    Fails closed for unknown capability slugs. The capability set is read from
    ``users.capabilities`` (cumulative JSONB). Non-site-admins without the
    granted capability are denied.
    """
    from apps.backend.domain.access.capabilities import (
        ALL_ADMIN_CAPABILITIES,
        evaluate_access,
    )

    if capability not in ALL_ADMIN_CAPABILITIES:
        raise HTTPException(status_code=403, detail=f"unknown capability: {capability}")
    user = await get_current_user(request)
    if not evaluate_access(
        site_role=db.user_site_role(user.id),
        capabilities=db.user_capabilities(user.id),
        capability=capability,
    ):
        raise HTTPException(status_code=403, detail="capability required")
    return user


async def require_admin_scope(request: Request, capability: str) -> AdminScope:
    """Require ``capability`` and return the tenant range it may act within.

    Same gate as :func:`require_admin_capability`, plus the confinement. The
    capability alone only says *what* kind of admin action is allowed, never
    *where* — a handler that creates, moves or grants against a target must check
    that target against the returned scope.
    """
    from apps.backend.domain.access.capabilities import AdminScope

    user = await require_admin_capability(request, capability)
    site_wide = (db.user_site_role(user.id) or "").strip().lower() == "site_admin"
    if site_wide:
        return AdminScope(actor_id=user.id, site_wide=True, tenant_ids=frozenset())
    return AdminScope(
        actor_id=user.id,
        site_wide=False,
        tenant_ids=frozenset({int(db.user_tenant_id(user.id) or 1)}),
    )


async def require_tenant_admin(request: Request) -> User:
    from apps.backend.infrastructure.settings import operator_settings

    user = await get_current_user(request)
    if not operator_settings.has_org_surface():
        raise HTTPException(
            status_code=404,
            detail="organization admin not available in this deployment mode",
        )
    tid = db.user_tenant_id(user.id)
    if db.user_is_tenant_admin(user.id, tid):
        return user
    raise HTTPException(status_code=403, detail="tenant admin required")


async def require_tenant_member(request: Request) -> User:
    """Any tenant membership (multi_tenant mode)."""
    from apps.backend.infrastructure.settings import operator_settings

    user = await get_current_user(request)
    if not operator_settings.has_org_surface():
        raise HTTPException(
            status_code=404,
            detail="organization not available in this deployment mode",
        )
    tid = db.user_tenant_id(user.id)
    if db.user_membership_role(user.id, tid) is None:
        raise HTTPException(status_code=403, detail="tenant membership required")
    return user


def require_permission(action: str, resource_type: Optional[str] = None) -> Callable:
    """
    Decorator to require permission for endpoint
    Example: @require_permission("execute", "tool")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            user = await get_current_user(request)

            # Site admin has all permissions
            if db.user_site_role(user.id) == "site_admin":
                return await func(request, *args, **kwargs, user=user)

            # Set identity context for downstream code (tenant from DB, never spoofable headers)
            id_token = set_identity(db.user_tenant_id(user.id), user.id)

            try:
                return await func(request, *args, **kwargs, user=user)
            finally:
                reset_identity(id_token)

        return wrapper
    return decorator


def insert_user_with_cursor(cur, email: str, password: str, role: str = "user", tenant_id: int = 1) -> User:
    """Insert a user row using an existing cursor (same transaction as caller)."""
    user_id = uuid.uuid4()
    password_hash = hash_password(password)
    external_sub = f"manual:{email}"
    site_role = "site_admin" if (role or "").strip().lower() == "admin" else "site_user"
    cur.execute(
        """
        INSERT INTO users (id, email, password_hash, role, site_role, tenant_id, external_sub)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING created_at
        """,
        (user_id, email, password_hash, role, site_role, tenant_id, external_sub),
    )
    created_at = cur.fetchone()[0]
    membership = "tenant_owner" if site_role == "site_admin" else "tenant_member"
    cur.execute(
        """
        INSERT INTO tenant_memberships (user_id, tenant_id, membership_role)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, tenant_id) DO UPDATE SET membership_role = EXCLUDED.membership_role
        """,
        (user_id, tenant_id, membership),
    )
    return User(
        id=user_id,
        email=email,
        role=role,
        created_at=created_at,
    )


def create_user(email: str, password: str, role: str = "user", tenant_id: int = 1) -> User:
    """Create new user."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            user = insert_user_with_cursor(cur, email, password, role, tenant_id=tenant_id)
            conn.commit()
    ensure_default_dashboard_for_new_user(user.id, tenant_id)
    return user


def update_user_tenant(user_id: uuid.UUID, tenant_id: int) -> bool:
    """Move a user to another tenant, keeping ``tenant_memberships`` in step.

    The membership row has to follow ``users.tenant_id`` — the two are read by
    different code paths and must not disagree. Goes through the guarded move,
    so a person still owning tenant-visible entities is refused rather than
    dragging company data into the new tenant.
    """
    return guarded_move_user_tenant(user_id, tenant_id)


def update_user_password(user_id: uuid.UUID, password: str) -> None:
    """Update existing user password"""
    # tenant-scope: site-wide — the caller holds the user id; password changes
    # are not tenant-partitioned.
    password_hash = hash_password(password)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
            """, (password_hash, user_id))
            conn.commit()
