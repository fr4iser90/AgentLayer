"""Postgres adapter for dashboard repository ports."""
from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.dashboards.entities import Dashboard
from apps.backend.domain.dashboards.repositories import DashboardRepository
from apps.backend.domain.dashboards.value_objects import DashboardId, DashboardKind, DashboardTitle
from apps.backend.infrastructure.dashboards import dashboard_db


class PostgresDashboardRepository(DashboardRepository):
    def create(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        kind: DashboardKind,
        title: DashboardTitle,
        template_id: str | None = None,
    ) -> Dashboard:
        row = dashboard_db.dashboard_create(
            owner_user_id,
            tenant_id,
            kind=str(kind),
            title=str(title),
            template_id=template_id,
        )
        return _dashboard_from_row(row)

    def get(
        self,
        dashboard_id: DashboardId,
        *,
        requester_user_id: uuid.UUID,
        tenant_id: int,
    ) -> Dashboard | None:
        row = dashboard_db.dashboard_get(requester_user_id, tenant_id, dashboard_id.value)
        return _dashboard_from_row(row) if row else None

    def list_for_user(
        self,
        *,
        tenant_id: int,
        user_id: uuid.UUID,
        limit: int = 200,
    ) -> list[Dashboard]:
        dashboards: list[Dashboard] = []
        for item in dashboard_db.dashboard_list(user_id, tenant_id, limit=limit):
            row = dashboard_db.dashboard_get(user_id, tenant_id, uuid.UUID(str(item["id"])))
            if row:
                dashboards.append(_dashboard_from_row(row))
        return dashboards

    def save(self, dashboard: Dashboard) -> Dashboard:
        row = dashboard_db.dashboard_update(
            dashboard.owner_user_id,
            dashboard.tenant_id,
            dashboard.id.value,
            title=str(dashboard.title),
            ui_layout=dashboard.ui_layout,
            data=dashboard.data,
        )
        if not row:
            raise ValueError("dashboard not found or not writable")
        return _dashboard_from_row(row)

    def delete(self, dashboard_id: DashboardId, *, owner_user_id: uuid.UUID, tenant_id: int) -> bool:
        return dashboard_db.dashboard_delete(owner_user_id, tenant_id, dashboard_id.value)


def _dashboard_from_row(row: dict[str, Any]) -> Dashboard:
    return Dashboard(
        id=DashboardId.parse(row["id"]),
        tenant_id=int(row.get("tenant_id") or 0),
        owner_user_id=uuid.UUID(str(row.get("owner_user_id") or row.get("owner_id"))),
        kind=DashboardKind.parse(str(row.get("kind") or "custom")),
        title=DashboardTitle.parse(str(row.get("title") or "Dashboard")),
        ui_layout=row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {"version": 2, "blocks": []},
        data=row.get("data") if isinstance(row.get("data"), dict) else {},
        template_id=str(row.get("template_id") or "").strip() or None,
    )
