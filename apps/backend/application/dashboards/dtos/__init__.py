"""Dashboard DTOs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardDto:
    id: uuid.UUID
    tenant_id: int
    owner_user_id: uuid.UUID
    kind: str
    title: str
    ui_layout: dict[str, Any]
    data: dict[str, Any]
    template_id: str | None = None
