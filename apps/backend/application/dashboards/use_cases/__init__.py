"""Dashboard use cases."""
from __future__ import annotations

from apps.backend.application.dashboards.commands import (
    CreateDashboardCommand,
    ReplaceDashboardDataCommand,
    ReplaceDashboardLayoutCommand,
)
from apps.backend.application.dashboards.dtos import DashboardDto
from apps.backend.application.dashboards.queries import GetDashboardQuery, ListDashboardsQuery
from apps.backend.domain.dashboards.entities import Dashboard
from apps.backend.domain.dashboards.repositories import DashboardRepository
from apps.backend.domain.dashboards.value_objects import DashboardId, DashboardKind, DashboardTitle


def _to_dto(dashboard: Dashboard) -> DashboardDto:
    return DashboardDto(
        id=dashboard.id.value,
        tenant_id=dashboard.tenant_id,
        owner_user_id=dashboard.owner_user_id,
        kind=str(dashboard.kind),
        title=str(dashboard.title),
        ui_layout=dashboard.ui_layout,
        data=dashboard.data,
        template_id=dashboard.template_id,
    )


def create_dashboard(repo: DashboardRepository, command: CreateDashboardCommand) -> DashboardDto:
    dashboard = repo.create(
        tenant_id=command.tenant_id,
        owner_user_id=command.owner_user_id,
        kind=DashboardKind.parse(command.kind),
        title=DashboardTitle.parse(command.title),
        template_id=command.template_id,
    )
    return _to_dto(dashboard)


def get_dashboard(repo: DashboardRepository, query: GetDashboardQuery) -> DashboardDto | None:
    dashboard = repo.get(
        DashboardId.parse(query.dashboard_id),
        requester_user_id=query.requester_user_id,
        tenant_id=query.tenant_id,
    )
    return _to_dto(dashboard) if dashboard is not None else None


def list_dashboards(repo: DashboardRepository, query: ListDashboardsQuery) -> list[DashboardDto]:
    return [
        _to_dto(dashboard)
        for dashboard in repo.list_for_user(
            tenant_id=query.tenant_id,
            user_id=query.user_id,
            limit=query.limit,
        )
    ]


def replace_dashboard_layout(
    repo: DashboardRepository,
    command: ReplaceDashboardLayoutCommand,
) -> DashboardDto | None:
    dashboard = repo.get(
        DashboardId.parse(command.dashboard_id),
        requester_user_id=command.requester_user_id,
        tenant_id=command.tenant_id,
    )
    if dashboard is None:
        return None
    dashboard.replace_layout(command.ui_layout)
    return _to_dto(repo.save(dashboard))


def replace_dashboard_data(
    repo: DashboardRepository,
    command: ReplaceDashboardDataCommand,
) -> DashboardDto | None:
    dashboard = repo.get(
        DashboardId.parse(command.dashboard_id),
        requester_user_id=command.requester_user_id,
        tenant_id=command.tenant_id,
    )
    if dashboard is None:
        return None
    dashboard.replace_data(command.data)
    return _to_dto(repo.save(dashboard))
