"""Dashboard commands."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CreateDashboardCommand:
    tenant_id: int
    owner_user_id: uuid.UUID
    kind: str = "custom"
    title: str = "Dashboard"
    template_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaceDashboardLayoutCommand:
    dashboard_id: uuid.UUID
    requester_user_id: uuid.UUID
    tenant_id: int
    ui_layout: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReplaceDashboardDataCommand:
    dashboard_id: uuid.UUID
    requester_user_id: uuid.UUID
    tenant_id: int
    data: dict[str, Any]
