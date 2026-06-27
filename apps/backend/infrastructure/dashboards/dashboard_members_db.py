from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards.dashboard_db import dashboard_can_manage_members
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import flatten_block_ids

def members_list(
    actor_user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Primary owner or co_owner may list members."""
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return []
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            if cur.fetchone() is None:
                conn.commit()
                return []
            cur.execute(
                """
                SELECT m.user_id, m.role, m.created_at, u.email
                FROM dashboard_members m
                JOIN users u ON u.id = m.user_id
                WHERE m.dashboard_id = %s
                ORDER BY m.created_at ASC
                """,
                (dashboard_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        uid, role, created, email = r[0], r[1], r[2], r[3]
        out.append(
            {
                "user_id": str(uid),
                "email": (email or "").strip(),
                "role": role,
                "created_at": created.isoformat() if isinstance(created, datetime) else str(created),
            }
        )
    return out


def member_add(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    member_user_id: uuid.UUID,
    role: str,
) -> bool:
    r = (role or "").strip().lower()
    if r not in ("viewer", "editor", "co_owner"):
        return False
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT owner_user_id FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            row = cur.fetchone()
            if row is None:
                conn.commit()
                return False
            primary_owner = row[0]
            if not isinstance(primary_owner, uuid.UUID):
                primary_owner = uuid.UUID(str(primary_owner))
            if member_user_id == primary_owner:
                return False
    mtid = db.user_tenant_id(member_user_id)
    if mtid != tenant_id:
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_members (dashboard_id, user_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (dashboard_id, user_id) DO UPDATE SET role = EXCLUDED.role
                """,
                (dashboard_id, member_user_id, r),
            )
        conn.commit()
    return True


def _layout_block_ids(ui_layout: dict[str, Any]) -> set[str]:
    return set(flatten_block_ids(ui_layout))


def block_share_grants_list(
    actor_user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> list[dict[str, Any]]:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return []
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT g.viewer_user_id, g.block_ids, g.created_at, u.email,
                  COALESCE(g.permission, 'view') AS permission
                FROM dashboard_block_share_grants g
                JOIN users u ON u.id = g.viewer_user_id
                WHERE g.dashboard_id = %s AND g.tenant_id = %s
                ORDER BY u.email ASC
                """,
                (dashboard_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    result: list[dict[str, Any]] = []
    for r in rows:
        uid, bid, created, email, perm_raw = r[0], r[1], r[2], r[3], r[4]
        perm = str(perm_raw or "view").strip().lower()
        if perm not in ("view", "edit"):
            perm = "view"
        result.append(
            {
                "user_id": str(uid),
                "email": (email or "").strip(),
                "block_ids": list(bid) if isinstance(bid, list) else [],
                "permission": perm,
                "created_at": created.isoformat() if isinstance(created, datetime) else str(created),
            }
        )
    return result


def block_share_grant_upsert(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    viewer_user_id: uuid.UUID,
    block_ids: list[str],
    permission: str = "view",
) -> bool:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return False
    perm = str(permission or "view").strip().lower()
    if perm not in ("view", "edit"):
        return False
    if db.user_tenant_id(viewer_user_id) != tenant_id:
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT owner_user_id, ui_layout FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return False
            owner_uid, ul = row[0], row[1]
            if not isinstance(owner_uid, uuid.UUID):
                owner_uid = uuid.UUID(str(owner_uid))
            if viewer_user_id == owner_uid:
                conn.commit()
                return False
            ui_layout = ul if isinstance(ul, dict) else {}
            valid = _layout_block_ids(ui_layout)
            cleaned = [str(x).strip() for x in block_ids if str(x).strip()]
            cleaned = [x for x in cleaned if x in valid]
            if not cleaned:
                conn.commit()
                return False
            cur.execute(
                """
                INSERT INTO dashboard_block_share_grants (
                  dashboard_id, viewer_user_id, tenant_id, block_ids, created_by, permission
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (dashboard_id, viewer_user_id)
                DO UPDATE SET
                  block_ids = EXCLUDED.block_ids,
                  created_by = EXCLUDED.created_by,
                  permission = EXCLUDED.permission
                """,
                (
                    dashboard_id,
                    viewer_user_id,
                    tenant_id,
                    cleaned,
                    actor_user_id,
                    perm,
                ),
            )
        conn.commit()
    return True


def block_share_grant_delete(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
) -> bool:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dashboard_block_share_grants
                WHERE dashboard_id = %s AND tenant_id = %s AND viewer_user_id = %s
                """,
                (dashboard_id, tenant_id, viewer_user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def member_remove(
    actor_user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    member_user_id: uuid.UUID,
) -> bool:
    if not dashboard_can_manage_members(actor_user_id, tenant_id, dashboard_id):
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT owner_user_id FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, tenant_id),
            )
            row = cur.fetchone()
            if row is None:
                conn.commit()
                return False
            primary_owner = row[0]
            if not isinstance(primary_owner, uuid.UUID):
                primary_owner = uuid.UUID(str(primary_owner))
            if member_user_id == primary_owner:
                return False
            cur.execute(
                """
                DELETE FROM dashboard_members
                WHERE dashboard_id = %s AND user_id = %s
                """,
                (dashboard_id, member_user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


