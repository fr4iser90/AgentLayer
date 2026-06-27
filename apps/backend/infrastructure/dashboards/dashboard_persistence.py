"""Infrastructure persistence helpers for dashboard/workspace ownership checks."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Literal, NamedTuple

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

AccessRole = Literal["owner", "co_owner", "editor", "viewer"]


class DashboardAccessDetail(NamedTuple):
    """``allowed_block_ids`` is ``None`` for full dashboard access."""

    role: AccessRole | None
    allowed_block_ids: frozenset[str] | None
    granular_can_write: bool


def dashboard_access_ex(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> DashboardAccessDetail:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.owner_user_id, m.role
                FROM user_dashboards w
                LEFT JOIN dashboard_members m
                  ON m.dashboard_id = w.id AND m.user_id = %s
                WHERE w.id = %s AND w.tenant_id = %s
                  AND (w.owner_user_id = %s OR m.user_id IS NOT NULL)
                """,
                (user_id, dashboard_id, tenant_id, user_id),
            )
            row = cur.fetchone()
            if row:
                owner_uid, member_role = row[0], row[1]
                if owner_uid == user_id:
                    return DashboardAccessDetail("owner", None, False)
                if member_role in ("co_owner", "editor", "viewer"):
                    return DashboardAccessDetail(member_role, None, False)
            cur.execute(
                """
                SELECT block_ids, COALESCE(permission, 'view') AS permission
                FROM dashboard_block_share_grants
                WHERE dashboard_id = %s AND viewer_user_id = %s AND tenant_id = %s
                """,
                (dashboard_id, user_id, tenant_id),
            )
            grow = cur.fetchone()
        conn.commit()
    if grow and grow[0]:
        raw_ids = grow[0]
        perm_raw = str(grow[1] or "view").strip().lower() if len(grow) > 1 else "view"
        bf = (
            frozenset(str(x).strip() for x in raw_ids if str(x).strip())
            if isinstance(raw_ids, list)
            else frozenset()
        )
        if bf:
            can_write = perm_raw == "edit"
            return DashboardAccessDetail("editor" if can_write else "viewer", bf, can_write)

    from apps.backend.domain.shares.dashboard_grant import friend_dashboard_access_detail

    friend_access = friend_dashboard_access_detail(user_id, dashboard_id)
    if friend_access is not None and friend_access.role is not None:
        return friend_access
    return DashboardAccessDetail(None, None, False)


def dashboard_access(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> AccessRole | None:
    return dashboard_access_ex(user_id, tenant_id, dashboard_id).role


def dashboard_has_full_access(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> bool:
    detail = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    return detail.role is not None and detail.allowed_block_ids is None


def dashboard_list(user_id: uuid.UUID, tenant_id: int, limit: int = 200) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.id, w.kind, w.template_id, w.title, w.updated_at, w.created_at,
                  CASE
                    WHEN w.owner_user_id = %s THEN 'owner'
                    WHEN m.role IS NOT NULL THEN m.role::text
                    WHEN g.viewer_user_id IS NOT NULL THEN
                      CASE
                        WHEN COALESCE(g.permission, 'view') = 'edit' THEN 'editor'
                        ELSE 'viewer'
                      END
                    ELSE 'owner'
                  END AS access_role
                FROM user_dashboards w
                LEFT JOIN dashboard_members m
                  ON m.dashboard_id = w.id AND m.user_id = %s
                LEFT JOIN dashboard_block_share_grants g
                  ON g.dashboard_id = w.id AND g.viewer_user_id = %s AND g.tenant_id = w.tenant_id
                WHERE w.tenant_id = %s
                  AND (
                    w.owner_user_id = %s
                    OR m.user_id IS NOT NULL
                    OR g.viewer_user_id IS NOT NULL
                  )
                ORDER BY w.updated_at DESC
                LIMIT %s
                """,
                (user_id, user_id, user_id, tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        wid = r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0]))
        did = str(wid)
        seen.add(did)
        role = (r[6] or "owner").strip().lower()
        if role not in ("owner", "co_owner", "editor", "viewer"):
            role = "owner"
        tpl = r[2]
        out.append(
            {
                "id": did,
                "kind": r[1],
                "template_id": (tpl or "").strip() if isinstance(tpl, str) else None,
                "title": r[3] or "",
                "updated_at": r[4].isoformat() if isinstance(r[4], datetime) else str(r[4]),
                "created_at": r[5].isoformat() if isinstance(r[5], datetime) else str(r[5]),
                "access_role": role,
            }
        )

    from apps.backend.domain.shares.dashboard_grant import list_friend_shared_dashboards

    for item in list_friend_shared_dashboards(user_id):
        if item.get("id") in seen:
            continue
        seen.add(str(item.get("id")))
        out.append(item)
    out.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return out[:limit]


def dashboard_delete(user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM user_dashboards
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                """,
                (dashboard_id, tenant_id, user_id),
            )
            ok = cur.fetchone() is not None
        conn.commit()
    if not ok:
        return False

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dashboard_members WHERE dashboard_id = %s", (dashboard_id,))
            cur.execute(
                """
                DELETE FROM user_dashboards
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s
                """,
                (dashboard_id, tenant_id, user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def dashboard_get(user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID) -> dict[str, Any] | None:
    detail = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    if detail.role is None:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, kind, template_id, title, ui_layout, data, view_bindings,
                       owner_user_id, tenant_id, created_at, updated_at
                FROM user_dashboards
                WHERE id = %s
                """,
                (dashboard_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    raw = dict(row)
    wid = raw.get("id")
    out = {
        "id": str(wid),
        "kind": raw.get("kind"),
        "template_id": raw.get("template_id"),
        "title": raw.get("title") or "",
        "ui_layout": raw.get("ui_layout") if isinstance(raw.get("ui_layout"), dict) else {},
        "data": raw.get("data") if isinstance(raw.get("data"), dict) else {},
        "view_bindings": raw.get("view_bindings") if isinstance(raw.get("view_bindings"), dict) else {},
        "owner_user_id": str(raw.get("owner_user_id") or ""),
        "tenant_id": int(raw.get("tenant_id") or tenant_id),
        "access_role": detail.role,
        "access_scope": "granular" if detail.allowed_block_ids is not None else "full",
        "created_at": raw.get("created_at").isoformat()
        if isinstance(raw.get("created_at"), datetime)
        else str(raw.get("created_at") or ""),
        "updated_at": raw.get("updated_at").isoformat()
        if isinstance(raw.get("updated_at"), datetime)
        else str(raw.get("updated_at") or ""),
    }
    if detail.allowed_block_ids is not None:
        out["allowed_block_ids"] = sorted(detail.allowed_block_ids)
        out["granular_can_write"] = detail.granular_can_write
    return out


def ensure_default_dashboard_for_new_user(user_id: uuid.UUID, tenant_id: int) -> None:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.user_dashboards')")
                if cur.fetchone()[0] is None:
                    conn.commit()
                    return
                cur.execute(
                    """
                    SELECT COUNT(*) FROM user_dashboards
                    WHERE owner_user_id = %s AND tenant_id = %s
                    """,
                    (user_id, tenant_id),
                )
                row = cur.fetchone()
                n = int(row[0]) if row and row[0] is not None else 0
                if n > 0:
                    conn.commit()
                    return
                cur.execute(
                    """
                    INSERT INTO user_dashboards (
                      tenant_id, owner_user_id, kind, template_id, title, ui_layout, data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tenant_id,
                        user_id,
                        "custom",
                        None,
                        "Personal dashboard",
                        Json({"version": 2, "blocks": []}),
                        Json({}),
                    ),
                )
            conn.commit()
    except Exception:
        logger.exception(
            "ensure_default_dashboard_for_new_user failed (user_id=%s tenant_id=%s)",
            user_id,
            tenant_id,
        )
