"""Identity entities."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.backend.domain.identity.value_objects import EmailAddress, TenantId, UserRole


@dataclass(frozen=True, slots=True)
class Tenant:
    id: TenantId
    name: str = "default"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tenant name is required")


@dataclass(slots=True)
class User:
    id: uuid.UUID
    tenant_id: TenantId
    email: EmailAddress
    role: UserRole
    created_at: datetime | None = None

    def is_admin(self) -> bool:
        return self.role == "admin"

    def change_role(self, role: UserRole) -> None:
        self.role = role
