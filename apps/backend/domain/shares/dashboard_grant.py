"""Resolve friend share grants for dashboard boards (cross-tenant)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.dashboard.db import DashboardAccessDetail
from apps.backend.domain.shares.policy import grant_is_active
from apps.backend.infrastructure.db.db import pool

_DASHBOARD_RESOURCE_TYPES = ("dashboard",)


def _row_policy(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _policy_block_ids(policy: dict[str, Any]) -> frozenset[str] | None:
    raw = policy.get("block_ids")
    if not isinstance(raw, list):
        return None
    cleaned = [str(x).strip() for x in raw if str(x).strip()]
    return frozenset(cleaned) if cleaned else None


def _policy_permission(policy: dict[str, Any]) -> str:
    perm = str(policy.get("permission") or "view").strip().lower()
    return perm if perm in ("view", "edit") else "view"


def grant_matches_dashboard(
    *,
    dashboard_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
    dashboard_kind: str,
) -> bool:
    ident = (resource_identifier or "primary").strip().lower()
    did = str(dashboard_id).strip().lower()
    return ident == did


def _access_from_policy(policy: dict[str, Any]) -> DashboardAccessDetail:
    perm = _policy_permission(policy)
    block_ids = _policy_block_ids(policy)
    if block_ids is not None:
        can_write = perm == "edit"
        role = "editor" if can_write else "viewer"
        return DashboardAccessDetail(role, block_ids, can_write)
    if perm == "edit":
        return DashboardAccessDetail("editor", None, False)
    return DashboardAccessDetail("viewer", None, False)


def friend_dashboard_access_detail(
    grantee_user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
) -> DashboardAccessDetail | None:
    """Return access from an active friend share grant, or None."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type, sp.resource_identifier,
                       sp.is_allowed, sp.policy, sp.revoked_at,
                       w.kind AS dashboard_kind
                FROM share_permissions sp
                JOIN user_dashboards w
                  ON w.owner_user_id = sp.owner_user_id AND w.id = %s
                WHERE sp.grantee_user_id = %s
                  AND sp.resource_type = ANY(%s)
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                ORDER BY sp.updated_at DESC
                """,
                (dashboard_id, grantee_user_id, list(_DASHBOARD_RESOURCE_TYPES)),
            )
            rows = cur.fetchall()

    for row in rows:
        policy = _row_policy(row.get("policy"))
        if not grant_is_active(
            is_allowed=bool(row.get("is_allowed")),
            revoked_at=row.get("revoked_at"),
            policy=policy,
        ):
            continue
        if not grant_matches_dashboard(
            dashboard_id=dashboard_id,
            resource_type=str(row.get("resource_type") or ""),
            resource_identifier=str(row.get("resource_identifier") or ""),
            dashboard_kind=str(row.get("dashboard_kind") or ""),
        ):
            continue
        return _access_from_policy(policy)
    return None


def list_friend_shared_dashboards(grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Dashboard summaries visible via friend share grants."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT w.id, w.kind, w.template_id, w.title, w.updated_at, w.created_at,
                       sp.policy, sp.resource_type, sp.resource_identifier
                FROM share_permissions sp
                JOIN user_dashboards w ON w.owner_user_id = sp.owner_user_id
                WHERE sp.grantee_user_id = %s
                  AND sp.resource_type = ANY(%s)
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                  AND (
                    lower(sp.resource_identifier) = lower(w.id::text)
                    OR (
                      sp.resource_type = 'pets'
                      AND w.kind = 'pets'
                      AND lower(sp.resource_identifier) = 'primary'
                    )
                  )
                ORDER BY w.updated_at DESC
                """,
                (grantee_user_id, list(_DASHBOARD_RESOURCE_TYPES)),
            )
            rows = cur.fetchall()

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        wid = row.get("id")
        if not isinstance(wid, uuid.UUID):
            wid = uuid.UUID(str(wid))
        did = str(wid)
        if did in seen:
            continue
        policy = _row_policy(row.get("policy"))
        if not grant_is_active(is_allowed=True, revoked_at=None, policy=policy):
            continue
        if not grant_matches_dashboard(
            dashboard_id=wid,
            resource_type=str(row.get("resource_type") or ""),
            resource_identifier=str(row.get("resource_identifier") or ""),
            dashboard_kind=str(row.get("dashboard_kind") or ""),
        ):
            continue
        seen.add(did)
        access = _access_from_policy(policy)
        tpl = row.get("template_id")
        ua = row.get("updated_at")
        ca = row.get("created_at")
        out.append(
            {
                "id": did,
                "kind": row.get("kind") or "",
                "template_id": (tpl or "").strip() if isinstance(tpl, str) else None,
                "title": row.get("title") or "",
                "updated_at": ua.isoformat() if isinstance(ua, datetime) else str(ua or ""),
                "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
                "access_role": access.role or "viewer",
                "access_via": "friend_share",
            }
        )
    return out


def dashboard_tenant_id(dashboard_id: uuid.UUID) -> int | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM user_dashboards WHERE id = %s",
                (dashboard_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return int(row[0])
