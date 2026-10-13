"""Link records between an AgentLayer user and their messaging ids (Discord, Telegram).

The normalizers run before a value reaches ``users.discord_user_id`` /
``users.telegram_user_id`` so a handle or a mention never lands in the column. The
per-tenant resolvers serve outbound delivery, where the tenant is already known; the
global ones serve the bridges, where an inbound message carries only the platform id and
the tenant has to come back with the user.
"""

from __future__ import annotations

import logging
import re
import uuid

from apps.backend.infrastructure.db.db import pool

logger = logging.getLogger(__name__)


_DISCORD_NUMERIC_USER_ID = re.compile(r"^[0-9]{15,22}$")


def discord_user_id_normalize(raw: str) -> str:
    s = (raw or "").strip()
    if not _DISCORD_NUMERIC_USER_ID.match(s):
        raise ValueError("Discord user id must be a numeric id (15–22 digits), from Copy User ID in Discord.")
    return s


def user_discord_user_id_get(user_id: uuid.UUID) -> str | None:  # tenant-scope: site-wide (pk lookup)
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


def user_telegram_user_id_get(user_id: uuid.UUID) -> str | None:  # tenant-scope: site-wide (pk lookup)
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
