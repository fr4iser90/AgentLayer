"""Dashboard queries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetDashboardQuery:
    dashboard_id: uuid.UUID
    requester_user_id: uuid.UUID
    tenant_id: int


@dataclass(frozen=True, slots=True)
class ListDashboardsQuery:
    tenant_id: int
    user_id: uuid.UUID
    limit: int = 200
