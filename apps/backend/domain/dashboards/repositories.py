"""Repository ports for the dashboard bounded context."""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.backend.domain.dashboards.entities import Dashboard, DashboardAccessGrant
from apps.backend.domain.dashboards.value_objects import DashboardId, DashboardKind, DashboardTitle


class DashboardRepository(Protocol):
    def create(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        kind: DashboardKind,
        title: DashboardTitle,
        template_id: str | None = None,
    ) -> Dashboard: ...

    def get(self, dashboard_id: DashboardId, *, requester_user_id: uuid.UUID, tenant_id: int) -> Dashboard | None: ...

    def list_for_user(
        self,
        *,
        tenant_id: int,
        user_id: uuid.UUID,
        limit: int = 200,
    ) -> list[Dashboard]: ...

    def save(self, dashboard: Dashboard) -> Dashboard: ...

    def delete(self, dashboard_id: DashboardId, *, owner_user_id: uuid.UUID, tenant_id: int) -> bool: ...


class DashboardAccessRepository(Protocol):
    def access_for(
        self,
        *,
        tenant_id: int,
        user_id: uuid.UUID,
        dashboard_id: DashboardId,
    ) -> DashboardAccessGrant | None: ...
