"""Identity DTOs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserDto:
    id: uuid.UUID
    tenant_id: int
    email: str
    role: str


@dataclass(frozen=True, slots=True)
class TenantDto:
    id: int
    name: str
