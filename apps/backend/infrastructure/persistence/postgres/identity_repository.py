"""Postgres adapters for identity repository ports."""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.domain.identity.entities import Tenant, User
from apps.backend.domain.identity.repositories import TenantRepository, UserRepository
from apps.backend.domain.identity.value_objects import EmailAddress, TenantId
from apps.backend.infrastructure.db import db


class PostgresUserRepository(UserRepository):
    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        with db.pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, tenant_id, email, role, created_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            conn.commit()
        return _user_from_row(dict(row)) if row else None

    def get_by_email(self, email: EmailAddress) -> User | None:
        with db.pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, tenant_id, email, role, created_at FROM users WHERE lower(email) = %s",
                    (str(email),),
                )
                row = cur.fetchone()
            conn.commit()
        return _user_from_row(dict(row)) if row else None

    def list_by_tenant(self, tenant_id: TenantId, *, limit: int = 100) -> list[User]:
        with db.pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, tenant_id, email, role, created_at
                    FROM users
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (int(tenant_id), int(limit)),
                )
                rows = cur.fetchall()
            conn.commit()
        return [_user_from_row(dict(row)) for row in rows]

    def save(self, user: User) -> User:
        with db.pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET email = %s, role = %s, tenant_id = %s
                    WHERE id = %s
                    RETURNING id, tenant_id, email, role, created_at
                    """,
                    (str(user.email), user.role, int(user.tenant_id), user.id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise ValueError("user not found")
        return _user_from_row(dict(row))


class PostgresTenantRepository(TenantRepository):
    def get(self, tenant_id: TenantId) -> Tenant | None:
        return Tenant(id=tenant_id, name=f"tenant-{int(tenant_id)}")

    def default(self) -> Tenant:
        return Tenant(id=TenantId(1), name="default")


def _user_from_row(row: dict[str, Any]) -> User:
    return User(
        id=uuid.UUID(str(row["id"])),
        tenant_id=TenantId(int(row.get("tenant_id") or 1)),
        email=EmailAddress.parse(str(row.get("email") or "")),
        role="admin" if str(row.get("role") or "").lower() == "admin" else "user",
        created_at=row.get("created_at"),
    )
