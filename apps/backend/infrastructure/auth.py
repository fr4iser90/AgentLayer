"""
Authentication & Authorization Layer for Agent Layer
JWT Access + Refresh Tokens, BCrypt Password Hashing, Permission System
"""
from __future__ import annotations

import os
import bcrypt
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Callable, Any

from fastapi import Request, HTTPException
from pydantic import BaseModel, Field

from apps.backend.infrastructure.db import db
from apps.backend.domain.identity import set_identity, reset_identity
from apps.backend.dashboard.db import ensure_default_dashboard_for_new_user


# JWT Configuration
JWT_SECRET = os.environ.get("AGENT_JWT_SECRET", os.urandom(32).hex())
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class User(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    password_hash: str | None = Field(default=None, exclude=True)
    ide_agent_allowed: bool = Field(
        default=False,
        description="Legacy DB column; ignored for access control. PIDEA / IDE Agent is admin-only.",
    )

    class Config:
        from_attributes = True


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


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Create long-lived refresh token, returns (token, token_hash)"""
    token = uuid.uuid4().hex
    token_hash = hash_password(token)
    return token, token_hash


def validate_refresh_token(token: str) -> Optional[User]:
    """Validate refresh token and return user if valid"""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, token_hash, expires_at
                FROM refresh_tokens
                WHERE expires_at > NOW()
            """)
            
            for row in cur.fetchall():
                user_id, token_hash, expires_at = row
                if verify_password(token, token_hash):
                    return get_user_by_id(user_id)
    
    return None


def revoke_refresh_token(token: str) -> bool:
    """Delete refresh session matching the raw token (e.g. on logout). Returns True if a row was removed."""
    if not (token or "").strip():
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, token_hash
                FROM refresh_tokens
                WHERE expires_at > NOW()
                """
            )
            for row in cur.fetchall():
                rid, token_hash = row
                if verify_password(token, token_hash):
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
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, role, created_at, password_hash, ide_agent_allowed
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
                ide_agent_allowed=bool(row[5]) if row[5] is not None else False,
            )


def list_all_users() -> list[dict[str, Any]]:
    """
    All ``users`` rows for admin UI. ``email`` is nullable in the schema; do not build ``User``
    here or Pydantic rejects NULL emails.
    """
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.role, u.created_at, u.external_sub, u.display_name,
                       u.tenant_id, t.name AS tenant_name, u.discord_user_id, u.telegram_user_id,
                       COALESCE(u.workspace_quota, 10) AS workspace_quota,
                       COALESCE(u.workspace_self_allowed, false) AS workspace_self_allowed
                FROM users u
                LEFT JOIN tenants t ON t.id = u.tenant_id
                ORDER BY u.created_at ASC NULLS LAST, u.email ASC NULLS LAST, u.external_sub ASC
                """
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        (
            uid,
            email,
            role,
            created_at,
            external_sub,
            display_name,
            tenant_id,
            tenant_name,
            discord_uid,
            telegram_uid,
            workspace_quota,
            workspace_self_allowed,
        ) = row
        tid = int(tenant_id) if tenant_id is not None else 1
        du = str(discord_uid).strip() if discord_uid is not None else ""
        tu = str(telegram_uid).strip() if telegram_uid is not None else ""
        out.append(
            {
                "id": str(uid),
                "email": email or "",
                "role": role,
                "created_at": created_at.isoformat() if created_at else "",
                "external_sub": external_sub,
                "display_name": display_name,
                "tenant_id": tid,
                "tenant_name": (tenant_name or "") if tenant_name is not None else "",
                "discord_user_id": du or None,
                "telegram_user_id": tu or None,
                "workspace_quota": workspace_quota if workspace_quota is not None else 10,
                "workspace_self_allowed": bool(workspace_self_allowed) if workspace_self_allowed is not None else False,
            }
        )
    return out


def get_user_by_id(user_id: uuid.UUID) -> Optional[User]:
    """Get user by id"""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, role, created_at, ide_agent_allowed
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
                ide_agent_allowed=bool(row[4]) if row[4] is not None else False,
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

    raise HTTPException(status_code=401, detail="Unauthorized")


def get_user_for_bearer_token(token: str) -> Optional[User]:
    """
    Resolve user from JWT access token or API key string (same rules as ``Authorization: Bearer``).
    For WebSockets where headers/query carry the token without a full ``Request`` cycle.
    """
    raw = (token or "").strip()
    if not raw:
        return None
    payload = decode_access_token(raw)
    if payload and payload.get("sub"):
        try:
            user = get_user_by_id(uuid.UUID(str(payload["sub"])))
            if user:
                return user
        except (ValueError, TypeError):
            pass
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM api_keys WHERE key_hash = %s",
                (raw,),
            )
            row = cur.fetchone()
            if row:
                user = get_user_by_id(row[0])
                if user:
                    cur.execute(
                        "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = %s",
                        (raw,),
                    )
                    conn.commit()
                    return user
    return None


async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin required")
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

            # Admin has all permissions
            if user.role == "admin":
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
    cur.execute(
        """
        INSERT INTO users (id, email, password_hash, role, tenant_id, external_sub)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING created_at
        """,
        (user_id, email, password_hash, role, tenant_id, external_sub),
    )
    created_at = cur.fetchone()[0]
    return User(
        id=user_id,
        email=email,
        role=role,
        created_at=created_at,
        ide_agent_allowed=False,
    )


def create_user(email: str, password: str, role: str = "user", tenant_id: int = 1) -> User:
    """Create new user."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            user = insert_user_with_cursor(cur, email, password, role, tenant_id=tenant_id)
            conn.commit()
    ensure_default_dashboard_for_new_user(user.id, tenant_id)
    return user


# def ide_agent_access_for_user(user: User) -> bool:
#     """True when PIDEA is globally on and the user is **admin** (direct IDE / Playwright control)."""
#     from apps.backend.infrastructure import operator_settings

#     if not operator_settings.pidea_effective_enabled():
#         return False
#     return (user.role or "").strip().lower() == "admin"


def update_user_ide_agent_allowed(user_id: uuid.UUID, allowed: bool) -> bool:
    """Set ``users.ide_agent_allowed`` (legacy column; **not** used for PIDEA access — admin-only)."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET ide_agent_allowed = %s WHERE id = %s",
                (allowed, user_id),
            )
            n = cur.rowcount or 0
            conn.commit()
    return n > 0


def update_user_tenant(user_id: uuid.UUID, tenant_id: int) -> bool:
    """Set ``users.tenant_id``. Returns True if a row was updated."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET tenant_id = %s WHERE id = %s",
                (tenant_id, user_id),
            )
            n = cur.rowcount or 0
            conn.commit()
    return n > 0


def update_user_password(user_id: uuid.UUID, password: str) -> None:
    """Update existing user password"""
    password_hash = hash_password(password)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
            """, (password_hash, user_id))
            conn.commit()
