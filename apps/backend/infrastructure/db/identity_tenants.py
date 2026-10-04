from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.domain.identity.roles import (
    ADMIN as ROLE_ADMIN,
    ELEVATED_SQL,
    SITE_ADMIN,
    USER as ROLE_USER,
    normalize_site_role,
)
from apps.backend.infrastructure.db.db import pool

logger = logging.getLogger(__name__)

def tenants_list() -> list[dict[str, Any]]:
    """All rows from ``tenants`` (for admin UI: ids used in tool allowlists and ``users.tenant_id``)."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, name, created_at
                FROM tenants
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        ca = d.get("created_at")
        if ca is not None and hasattr(ca, "isoformat"):
            d["created_at"] = ca.isoformat()
        out.append(d)
    return out


def tenant_exists(tenant_id: int) -> bool:
    if tenant_id < 1:
        return False
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_id,))
            ok = cur.fetchone() is not None
        conn.commit()
    return ok


def tenant_insert(name: str) -> dict[str, Any]:
    """Insert a tenant row; ``name`` trim, fallback label if empty."""
    label = (name or "").strip() or "tenant"
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO tenants (name) VALUES (%s) RETURNING id, name, created_at",
                (label,),
            )
            row = cur.fetchone()
        conn.commit()
    d = dict(row)
    ca = d.get("created_at")
    if ca is not None and hasattr(ca, "isoformat"):
        d["created_at"] = ca.isoformat()
    return d


def user_external_sub(user_id: uuid.UUID) -> str | None:  # tenant-scope: site-wide (pk lookup)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT external_sub FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return str(row[0]) if row[0] is not None else None


def user_tenant_id(user_id: uuid.UUID) -> int:
    """``users.tenant_id`` for FK-scoped data and tool policy (defaults to ``1``)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return 1
    try:
        t = int(row[0])
    except (TypeError, ValueError):
        return 1
    return t if t >= 1 else 1


def user_first_admin_id() -> uuid.UUID | None:
    """Oldest elevated user (for bootstrap jobs that need an owning user id).

    Elevation is the domain rule, not the compatibility column: ``ELEVATED_SQL`` lets
    ``users.role`` speak only for a row that was never migrated, so an account demoted
    through ``site_role='site_user'`` cannot become the owner of new work.
    """
    with pool().connection() as conn:  # tenant-scope: site-wide — bootstrap has no tenant context
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id FROM users WHERE {ELEVATED_SQL} ORDER BY created_at ASC LIMIT 1"
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def user_site_role(user_id: uuid.UUID | None) -> str:  # tenant-scope: site-wide (pk lookup)
    """The one read behind every role answer: ``users.site_role``, legacy column only when unmigrated."""
    site, _legacy = _role_columns(user_id)
    return normalize_site_role(site, _legacy)


def user_site_admin(user_id: uuid.UUID | None) -> bool:
    """
    Canonical site-admin flag derived from ``users.site_role``.

    A definitive ``True``/``False`` for any user: ``users.role='admin'`` is honoured only
    when ``site_role`` is NULL/unknown, matching :func:`user_site_role`, so
    ``role='admin'`` with ``site_role='site_user'`` never elevates. An identity that
    cannot be read — no id, no row, a failing query — is not an admin either. Used by
    agent-elevation and workspace/admin gates.
    """
    return user_site_role(user_id) == SITE_ADMIN


def user_effective_role(user_id: uuid.UUID | None) -> str:
    """``user``/``admin`` for every role-word door, read from ``users.site_role``.

    ``users.role`` decides nothing here: :func:`user_site_role` lets the compatibility
    column speak only for a row that was never migrated, so a demoted account still
    carrying ``role='admin'`` loses the operator consoles.
    """
    return ROLE_ADMIN if user_site_role(user_id) == SITE_ADMIN else ROLE_USER


def _role_columns(user_id: uuid.UUID | None) -> tuple[str | None, str | None]:
    """``(users.site_role, users.role)`` for one row — the pair behind every role answer.

    Both columns travel together so no reader has to know which of them a rule prefers;
    a missing row, a missing id and a failing query all read ``(None, None)``, which the
    domain rule normalizes to the unelevated answer.
    """
    if user_id is None:
        return (None, None)
    try:
        with pool().connection() as conn:
            with conn.cursor() as cur:
                # tenant-scope: site-wide — canonical identity lookup by pk; callers decide
                # what the user's tenant permits, exactly as ``auth.get_user_by_id`` does.
                cur.execute(
                    "SELECT site_role, role FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            conn.commit()
    except Exception:  # noqa: BLE001 - an unreadable identity is never an elevation
        logger.exception("role columns unread for user=%s", user_id)
        return (None, None)
    if not row:
        return (None, None)
    return (str(row[0]) if row[0] is not None else None, str(row[1]) if row[1] is not None else None)


def scheduler_outbound_count_today_utc(user_id: uuid.UUID) -> int:
    """Rows in ``scheduler_outbound_daily`` for today's UTC date."""
    day = datetime.now(UTC).date()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT outbound_count FROM scheduler_outbound_daily WHERE user_id = %s AND day_utc = %s",
                (user_id, day),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def scheduler_outbound_increment_utc(user_id: uuid.UUID) -> int:
    """Upsert +1 for today UTC; returns new count."""
    day = datetime.now(UTC).date()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduler_outbound_daily (user_id, day_utc, outbound_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, day_utc) DO UPDATE SET
                  outbound_count = scheduler_outbound_daily.outbound_count + 1
                RETURNING outbound_count
                """,
                (user_id, day),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return 1
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 1


_TENANT_ADMIN_ROLES = frozenset({"tenant_owner", "tenant_admin"})


def user_capabilities(user_id: uuid.UUID | None) -> list[str]:
    """Per-user platform/admin capabilities (P6, Weg B). Always returns a list.

    ``users.capabilities`` is a JSONB array of slugs. Empty/unknown users yield
    ``[]`` so callers never have to guard for NULL.
    """
    if user_id is None:  # tenant-scope: site-wide (pk lookup)
        return []
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(capabilities, '[]'::jsonb) FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return []
    raw = row[0]
    if isinstance(raw, (list, tuple)):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    return []


def user_membership_role(user_id: uuid.UUID, tenant_id: int | None = None) -> str | None:
    tid = tenant_id if tenant_id is not None else user_tenant_id(user_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT membership_role FROM tenant_memberships
                WHERE user_id = %s AND tenant_id = %s
                """,
                (user_id, tid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    return str(row[0]).strip().lower()


def tenant_membership_upsert(
    user_id: uuid.UUID,
    tenant_id: int,
    membership_role: str,
) -> None:
    """Insert or replace a membership; it must match the user's home tenant.

    ``tenant_memberships`` and ``users.tenant_id`` are read by different code
    paths: ``require_tenant_member`` consults the membership row, while
    ``resolve_chat_identity`` reads ``users.tenant_id``. A row that disagrees
    with the home tenant lets a user pass the entry check while every write
    still lands in their home tenant — a ghost membership that silently mixes
    up who may be where. Moves go through ``update_user_tenant``, which keeps
    the two in step.
    """
    role = (membership_role or "tenant_member").strip().lower()
    if role not in ("tenant_owner", "tenant_admin", "tenant_member"):
        role = "tenant_member"
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"unknown user {user_id}")
            home = int(row[0])
            if home != int(tenant_id):
                raise ValueError(
                    f"tenant {tenant_id} is not the home tenant of user {user_id} "
                    f"(home is {home}); move the user instead of adding a membership"
                )
            cur.execute(
                """
                INSERT INTO tenant_memberships (user_id, tenant_id, membership_role)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, tenant_id) DO UPDATE SET
                  membership_role = EXCLUDED.membership_role
                """,
                (user_id, tenant_id, role),
            )
        conn.commit()


def move_user_tenant(user_id: uuid.UUID, tenant_id: int) -> bool:
    """Move a user to another tenant and keep ``tenant_memberships`` in step.

    The membership row has to follow ``users.tenant_id`` — the two are read by
    different code paths and must not disagree. The old role never carries over:
    the moved person arrives as ``tenant_member``; grant a new role explicitly.
    """
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return False
            previous = int(row[0])
            cur.execute("UPDATE users SET tenant_id = %s WHERE id = %s", (tenant_id, user_id))
            n = cur.rowcount or 0
            if n and previous != int(tenant_id):
                cur.execute(
                    "DELETE FROM tenant_memberships WHERE user_id = %s AND tenant_id <> %s",
                    (user_id, tenant_id),
                )
                cur.execute(
                    "INSERT INTO tenant_memberships (user_id, tenant_id, membership_role) "
                    "VALUES (%s, %s, %s) ON CONFLICT (user_id, tenant_id) "
                    "DO UPDATE SET membership_role = EXCLUDED.membership_role",
                    (user_id, tenant_id, "tenant_member"),
                )
                cur.execute("UPDATE project_workspaces SET tenant_id = %s WHERE owner_user_id = %s", (tenant_id, user_id))
            conn.commit()
    return n > 0


def tenant_get(tenant_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, name, created_at, setup_completed_at, vertical_profile
                FROM tenants WHERE id = %s
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    d = dict(row)
    for key in ("created_at", "setup_completed_at"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


def tenant_update_org_profile(
    tenant_id: int,
    *,
    name: str | None = None,
    vertical_profile: str | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = %s")
        params.append((name or "").strip() or "tenant")
    if vertical_profile is not None:
        sets.append("vertical_profile = %s")
        params.append((vertical_profile or "").strip() or None)
    if not sets:
        return tenant_get(tenant_id)
    params.append(tenant_id)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"UPDATE tenants SET {', '.join(sets)} WHERE id = %s RETURNING id, name, created_at, setup_completed_at, vertical_profile",
                tuple(params),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    d = dict(row)
    for key in ("created_at", "setup_completed_at"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


def tenant_mark_setup_completed(tenant_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE tenants SET setup_completed_at = COALESCE(setup_completed_at, now())
                WHERE id = %s
                RETURNING id, name, created_at, setup_completed_at, vertical_profile
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    d = dict(row)
    for key in ("created_at", "setup_completed_at"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


def user_is_tenant_admin(user_id: uuid.UUID, tenant_id: int | None = None) -> bool:
    role = user_membership_role(user_id, tenant_id)
    return role in _TENANT_ADMIN_ROLES

