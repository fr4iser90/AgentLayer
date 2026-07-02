from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row

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


def user_external_sub(user_id: uuid.UUID) -> str | None:
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
    """Oldest user with ``role = 'admin'`` (for bootstrap jobs that need an owning user id)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


_DISCORD_NUMERIC_USER_ID = re.compile(r"^[0-9]{15,22}$")


def discord_user_id_normalize(raw: str) -> str:
    s = (raw or "").strip()
    if not _DISCORD_NUMERIC_USER_ID.match(s):
        raise ValueError("Discord user id must be a numeric id (15–22 digits), from Copy User ID in Discord.")
    return s


def user_discord_user_id_get(user_id: uuid.UUID) -> str | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_user_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    out = str(row[0]).strip()
    return out or None


def user_discord_user_id_set(user_id: uuid.UUID, tenant_id: int, raw: str) -> str | None:
    """
    Set or clear ``users.discord_user_id``. Empty / whitespace ``raw`` clears the link.
    Returns the stored value (or None if cleared).
    """
    stripped = (raw or "").strip()
    new_val: str | None = None if not stripped else discord_user_id_normalize(stripped)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users SET discord_user_id = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (new_val, user_id, tenant_id),
            )
            if (cur.rowcount or 0) < 1:
                raise ValueError("user not found")
        conn.commit()
    return new_val


def user_id_for_discord_user_id(tenant_id: int, discord_user_id: str) -> uuid.UUID | None:
    """Resolve AgentLayer user id from Discord numeric user id within a tenant (for bots with DB access)."""
    sid = discord_user_id_normalize(discord_user_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND discord_user_id = %s",
                (tenant_id, sid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def user_id_tenant_for_discord_global(discord_user_id: str) -> tuple[uuid.UUID, int] | None:
    """
    Resolve (user_id, tenant_id) from a linked Discord numeric user id (any tenant).
    Returns None if unlinked, invalid id, or more than one row (ambiguous).
    """
    try:
        sid = discord_user_id_normalize(discord_user_id)
    except ValueError:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tenant_id FROM users WHERE discord_user_id = %s",
                (sid,),
            )
            rows = cur.fetchall()
        conn.commit()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "multiple users share the same discord_user_id; Discord bridge refuses ambiguous resolution"
        )
        return None
    uid, tid = rows[0]
    user_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    try:
        tenant_id = int(tid) if tid is not None else 1
    except (TypeError, ValueError):
        tenant_id = 1
    return user_uuid, tenant_id if tenant_id >= 1 else 1


_TELEGRAM_NUMERIC_USER_ID = re.compile(r"^[0-9]{5,20}$")


def telegram_user_id_normalize(raw: str) -> str:
    s = (raw or "").strip()
    if not _TELEGRAM_NUMERIC_USER_ID.match(s):
        raise ValueError(
            "Telegram user id must be numeric (5–20 digits). Use @userinfobot or Telegram settings to get your id."
        )
    return s


def user_telegram_user_id_get(user_id: uuid.UUID) -> str | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_user_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    out = str(row[0]).strip()
    return out or None


def user_telegram_user_id_set(user_id: uuid.UUID, tenant_id: int, raw: str) -> str | None:
    """
    Set or clear ``users.telegram_user_id``. Empty / whitespace ``raw`` clears the link.
    Returns the stored value (or None if cleared).
    """
    stripped = (raw or "").strip()
    new_val: str | None = None if not stripped else telegram_user_id_normalize(stripped)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users SET telegram_user_id = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (new_val, user_id, tenant_id),
            )
            if (cur.rowcount or 0) < 1:
                raise ValueError("user not found")
        conn.commit()
    return new_val


def user_id_for_telegram_user_id(tenant_id: int, telegram_user_id: str) -> uuid.UUID | None:
    """Resolve AgentLayer user id from Telegram user id within a tenant (for bots with DB access)."""
    sid = telegram_user_id_normalize(telegram_user_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND telegram_user_id = %s",
                (tenant_id, sid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def user_id_tenant_for_telegram_global(telegram_user_id: str) -> tuple[uuid.UUID, int] | None:
    """
    Resolve (user_id, tenant_id) from a linked Telegram user id (any tenant).
    Returns None if unlinked, invalid id, or more than one row (ambiguous).
    """
    try:
        sid = telegram_user_id_normalize(telegram_user_id)
    except ValueError:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tenant_id FROM users WHERE telegram_user_id = %s",
                (sid,),
            )
            rows = cur.fetchall()
        conn.commit()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "multiple users share the same telegram_user_id; Telegram bridge refuses ambiguous resolution"
        )
        return None
    uid, tid = rows[0]
    user_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    try:
        tenant_id = int(tid) if tid is not None else 1
    except (TypeError, ValueError):
        tenant_id = 1
    return user_uuid, tenant_id if tenant_id >= 1 else 1


def user_role(user_id: uuid.UUID | None) -> str:
    """Return ``users.role`` (``user`` or ``admin``) for tool access checks."""
    if user_id is None:
        return "user"
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return "user"
    r = str(row[0]).strip().lower()
    return r if r in ("user", "admin") else "user"


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


def user_site_role(user_id: uuid.UUID | None) -> str:
    if user_id is None:
        return "site_user"
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT site_role, role FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return "site_user"
    site = str(row[0] or "").strip().lower()
    if site in ("site_admin", "site_user"):
        return site
    legacy = str(row[1] or "").strip().lower()
    return "site_admin" if legacy == "admin" else "site_user"


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
    role = (membership_role or "tenant_member").strip().lower()
    if role not in ("tenant_owner", "tenant_admin", "tenant_member"):
        role = "tenant_member"
    with pool().connection() as conn:
        with conn.cursor() as cur:
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

