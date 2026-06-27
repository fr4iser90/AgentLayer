"""Infrastructure adapter for dashboard friend-share grants."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.domain.shares import dashboard_grant as domain
from apps.backend.infrastructure.db.db import pool


class _DashboardGrantDeps:
    @staticmethod
    def friend_dashboard_grant_rows(
        grantee_user_id: uuid.UUID,
        dashboard_id: uuid.UUID,
        resource_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
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
                    (dashboard_id, grantee_user_id, list(resource_types)),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def friend_shared_dashboard_rows(
        grantee_user_id: uuid.UUID,
        resource_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
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
                    (grantee_user_id, list(resource_types)),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
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


domain.register_dashboard_grant_dependencies(_DashboardGrantDeps())

dashboard_tenant_id = domain.dashboard_tenant_id
friend_dashboard_access_detail = domain.friend_dashboard_access_detail
list_friend_shared_dashboards = domain.list_friend_shared_dashboards
