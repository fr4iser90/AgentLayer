"""Dashboard aggregate roots and access entities."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.backend.domain.dashboards.schemas import validate_dashboard_data, validate_ui_layout
from apps.backend.domain.dashboards.value_objects import (
    DashboardId,
    DashboardKind,
    DashboardRole,
    DashboardTitle,
)


@dataclass(slots=True)
class DashboardAccessGrant:
    dashboard_id: DashboardId
    user_id: uuid.UUID
    role: DashboardRole
    allowed_block_ids: frozenset[str] | None = None
    granular_can_write: bool = False

    def can_write(self) -> bool:
        return self.role in ("owner", "co_owner", "editor") and (
            self.allowed_block_ids is None or self.granular_can_write
        )


@dataclass(slots=True)
class Dashboard:
    id: DashboardId
    tenant_id: int
    owner_user_id: uuid.UUID
    kind: DashboardKind
    title: DashboardTitle
    ui_layout: dict[str, Any] = field(default_factory=lambda: {"version": 2, "blocks": []})
    data: dict[str, Any] = field(default_factory=dict)
    template_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.tenant_id <= 0:
            raise ValueError("tenant_id must be positive")
        validate_ui_layout(self.ui_layout)
        validate_dashboard_data(self.data)

    def rename(self, title: DashboardTitle) -> None:
        self.title = title

    def replace_layout(self, ui_layout: dict[str, Any]) -> None:
        validate_ui_layout(ui_layout)
        self.ui_layout = ui_layout

    def replace_data(self, data: dict[str, Any]) -> None:
        validate_dashboard_data(data)
        self.data = data
