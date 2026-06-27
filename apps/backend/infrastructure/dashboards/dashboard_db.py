"""CRUD for ``user_dashboards`` (generic kind + ui_layout + data) and sharing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Literal, NamedTuple

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.dashboards.dashboard_defaults import defaults_for_kind
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import (
    data_paths_from_blocks,
    filter_layout_blocks,
    flatten_block_ids,
)

logger = logging.getLogger(__name__)

AccessRole = Literal["owner", "co_owner", "editor", "viewer"]


class DashboardAccessDetail(NamedTuple):
    """``allowed_block_ids`` is ``None`` for full dashboard (not granular)."""

    role: AccessRole | None
    allowed_block_ids: frozenset[str] | None
    granular_can_write: bool


def dashboard_access_ex(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> DashboardAccessDetail:
    """Effective role, optional block allowlist, and whether granular edit is allowed."""
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
                if member_role == "co_owner":
                    return DashboardAccessDetail("co_owner", None, False)
                if member_role == "editor":
                    return DashboardAccessDetail("editor", None, False)
                if member_role == "viewer":
                    return DashboardAccessDetail("viewer", None, False)
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
        if isinstance(raw_ids, list):
            bf = frozenset(str(x).strip() for x in raw_ids if str(x).strip())
        else:
            bf = frozenset()
        if bf:
            can_write = perm_raw == "edit"
            eff: AccessRole = "editor" if can_write else "viewer"
            return DashboardAccessDetail(eff, bf, can_write)

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
    """True if the user is owner or a normal member — not block-only granular access."""
    d = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    return d.role is not None and d.allowed_block_ids is None


from apps.backend.infrastructure.dashboards.dashboard_granular_update_db import (
    _dashboard_update_granular,
    _filter_data_for_visible_blocks,
    _filter_ui_layout,
)
def dashboard_can_manage_members(
    user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID
) -> bool:
    """Primary owner or co_owner may list/add/remove dashboard members."""
    role = dashboard_access(user_id, tenant_id, dashboard_id)
    return role == "owner" or role == "co_owner"


def dashboard_create(
    user_id: uuid.UUID,
    tenant_id: int,
    *,
    kind: str,
    title: str,
    template_id: str | None = None,
    ui_layout: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tpl = (template_id or "").strip().lower() or None
    du, dd = defaults_for_kind(kind, template_id=tpl)
    if ui_layout is not None:
        du = ui_layout
    if data is not None:
        dd = data
    from apps.backend.domain.shared.identity import get_benchmark_run_id

    label = (title or "").strip() or "Dashboard"
    bench_run_id = benchmark_run_id or get_benchmark_run_id()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_dashboards (
                  tenant_id, owner_user_id, kind, template_id, title, ui_layout, data, benchmark_run_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, kind, template_id, title, ui_layout, data, created_at, updated_at
                """,
                (
                    tenant_id,
                    user_id,
                    kind.strip() or "custom",
                    tpl,
                    label,
                    Json(du),
                    Json(dd),
                    bench_run_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    r = _row_dict(dict(row) if row else {})
    r["access_role"] = "owner"
    return r


def ensure_default_dashboard_for_new_user(user_id: uuid.UUID, tenant_id: int) -> None:
    """
    When ``user_dashboards`` exists, create one dashboard if this user owns none.

    Uses ``personal_dashboard`` when that bundle template is on disk; otherwise ``custom``.
    Skips silently if the dashboard schema is not installed yet. Logs and swallows errors so
    user signup still succeeds.
    """
    from apps.backend.infrastructure.dashboards.dashboard_bootstrap import dashboard_tables_exist
    from apps.backend.infrastructure.dashboards.dashboard_bundle import template_path_for_kind

    if not dashboard_tables_exist():
        return
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM user_dashboards
                WHERE owner_user_id = %s AND tenant_id = %s
                """,
                (user_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    n = int(row[0]) if row and row[0] is not None else 0
    if n > 0:
        return
    preferred = "personal_dashboard"
    kind = preferred if template_path_for_kind(preferred) is not None else "custom"
    tpl = f"{preferred}-v1" if kind == preferred else None
    try:
        dashboard_create(
            user_id,
            tenant_id,
            kind=kind,
            template_id=tpl,
            title="Personal dashboard",
        )
    except Exception:
        logger.exception(
            "ensure_default_dashboard_for_new_user failed (user_id=%s tenant_id=%s)",
            user_id,
            tenant_id,
        )


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
        wid = r[0]
        if not isinstance(wid, uuid.UUID):
            wid = uuid.UUID(str(wid))
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


def _row_dict(r: dict[str, Any]) -> dict[str, Any]:
    if not r:
        return {}
    wid = r.get("id")
    if not isinstance(wid, uuid.UUID):
        wid = uuid.UUID(str(wid))
    ul = r.get("ui_layout")
    dt = r.get("data")
    ca = r.get("created_at")
    ua = r.get("updated_at")
    tpl = r.get("template_id")
    return {
        "id": str(wid),
        "kind": r.get("kind") or "",
        "template_id": (tpl or "").strip() if isinstance(tpl, str) and tpl else None,
        "title": r.get("title") or "",
        "ui_layout": ul if isinstance(ul, dict) else {},
        "data": dt if isinstance(dt, dict) else {},
        "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
        "updated_at": ua.isoformat() if isinstance(ua, datetime) else str(ua or ""),
    }


def _dashboard_row_tenant_id(dashboard_id: uuid.UUID) -> int | None:
    from apps.backend.domain.shares.dashboard_grant import dashboard_tenant_id

    return dashboard_tenant_id(dashboard_id)


def dashboard_get(user_id: uuid.UUID, tenant_id: int, dashboard_id: uuid.UUID) -> dict[str, Any] | None:
    d = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    if d.role is None:
        return None
    row_tid = _dashboard_row_tenant_id(dashboard_id)
    if row_tid is None:
        return None
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, kind, template_id, title, ui_layout, data, view_bindings,
                       owner_user_id, tenant_id, created_at, updated_at
                FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (dashboard_id, row_tid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    raw = dict(row)
    legacy_data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    out = _row_dict(raw)
    out["owner_user_id"] = str(raw.get("owner_user_id") or "")
    out["tenant_id"] = int(raw.get("tenant_id") or row_tid)
    vb = raw.get("view_bindings")
    out["view_bindings"] = vb if isinstance(vb, dict) else {}

    from apps.backend.infrastructure.collections.collections_view_service import project_dashboard_data

    owner_uid = raw.get("owner_user_id")
    if isinstance(owner_uid, uuid.UUID):
        owner_uuid = owner_uid
    else:
        try:
            owner_uuid = uuid.UUID(str(owner_uid))
        except (ValueError, TypeError):
            owner_uuid = user_id

    out["data"] = project_dashboard_data(
        dashboard_id=dashboard_id,
        owner_user_id=owner_uuid,
        tenant_id=int(raw.get("tenant_id") or row_tid),
        ui_layout=out.get("ui_layout") if isinstance(out.get("ui_layout"), dict) else {},
        view_bindings=out["view_bindings"],
        template_id=out.get("template_id"),
        legacy_data=legacy_data,
    )
    out["data_source"] = "domain"
    out["access_role"] = d.role
    if d.allowed_block_ids is not None:
        ul = out.get("ui_layout") if isinstance(out.get("ui_layout"), dict) else {}
        out["ui_layout"] = _filter_ui_layout(ul, d.allowed_block_ids)
        dt = out.get("data") if isinstance(out.get("data"), dict) else {}
        out["data"] = _filter_data_for_visible_blocks(dt, out["ui_layout"])
        out["access_scope"] = "granular"
        out["allowed_block_ids"] = sorted(d.allowed_block_ids)
        out["granular_can_write"] = d.granular_can_write
    else:
        out["access_scope"] = "full"
    return out


def dashboard_update(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    title: str | None = None,
    ui_layout: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    d = dashboard_access_ex(user_id, tenant_id, dashboard_id)
    if d.role is None:
        return None
    row_tid = _dashboard_row_tenant_id(dashboard_id)
    if row_tid is None:
        return None
    if d.allowed_block_ids is not None:
        if not d.granular_can_write:
            return None
        return _dashboard_update_granular(
            user_id,
            row_tid,
            dashboard_id,
            title=title,
            ui_layout=ui_layout,
            data=data,
            allowed=d.allowed_block_ids,
        )
    if d.role == "viewer":
        return None
    role = d.role
    sets: list[str] = []
    args: list[Any] = []
    if title is not None:
        sets.append("title = %s")
        args.append((title or "").strip() or "Dashboard")
    if ui_layout is not None:
        sets.append("ui_layout = %s")
        args.append(Json(ui_layout))
    # Domain collections are source of truth — do not persist board content in user_dashboards.data.
    if data is not None:
        logger.debug(
            "dashboard_update ignored data payload for %s (use domain collections)",
            dashboard_id,
        )
    if not sets:
        return dashboard_get(user_id, tenant_id, dashboard_id)
    sets.append("updated_at = now()")
    args.extend([dashboard_id, row_tid, user_id, user_id])
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # SECURITY: Column names in `sets` come from function parameters (ui_layout, data).
            # SET fragments are fixed literals; all values are parameterized via %s placeholders.
            cur.execute(  # nosec B608  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query
                f"""
                UPDATE user_dashboards w
                SET {", ".join(sets)}
                WHERE w.id = %s AND w.tenant_id = %s
                  AND (
                    w.owner_user_id = %s
                    OR EXISTS (
                      SELECT 1 FROM dashboard_members m
                      WHERE m.dashboard_id = w.id AND m.user_id = %s
                        AND m.role IN ('editor', 'co_owner')
                    )
                  )
                RETURNING w.id, w.kind, w.template_id, w.title, w.ui_layout, w.data, w.created_at, w.updated_at
                """,
                args,
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    out = _row_dict(dict(row))
    out["access_role"] = role
    return out


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
            cur.execute(
                "DELETE FROM dashboard_members WHERE dashboard_id = %s",
                (dashboard_id,),
            )
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


from apps.backend.infrastructure.dashboards.dashboard_members_db import (
    block_share_grant_delete,
    block_share_grant_upsert,
    block_share_grants_list,
    member_add,
    member_remove,
    members_list,
)
_INSTALLED_TEMPLATE_KINDS_SQL = """
CREATE TABLE IF NOT EXISTS tenant_dashboard_installed_template_kinds (
  tenant_id BIGINT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  kinds TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);
"""


def ensure_tenant_installed_template_kinds_table() -> None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_INSTALLED_TEMPLATE_KINDS_SQL)
        conn.commit()


def tenant_installed_template_kinds(tenant_id: int) -> list[str] | None:
    """Which disk templates this tenant has installed, or ``None`` if unset (legacy: show all)."""
    ensure_tenant_installed_template_kinds_table()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT kinds FROM tenant_dashboard_installed_template_kinds WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    if row[0] is None:
        return None
    return [str(x).strip().lower() for x in row[0]]


def tenant_merge_installed_template_kinds(tenant_id: int, kinds: list[str]) -> None:
    """Record additional installed template kinds (distinct). ``custom`` is ignored."""
    ensure_tenant_installed_template_kinds_table()
    add = sorted(
        {
            str(k).strip().lower()
            for k in kinds
            if str(k).strip() and str(k).strip().lower() != "custom"
        }
    )
    if not add:
        return
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT kinds FROM tenant_dashboard_installed_template_kinds WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            existing: list[str] = []
            if row and row[0]:
                existing = [str(x).strip().lower() for x in row[0]]
            merged = sorted(set(existing + add))
            cur.execute(
                """
                INSERT INTO tenant_dashboard_installed_template_kinds (tenant_id, kinds)
                VALUES (%s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET kinds = EXCLUDED.kinds
                """,
                (tenant_id, merged),
            )
        conn.commit()
