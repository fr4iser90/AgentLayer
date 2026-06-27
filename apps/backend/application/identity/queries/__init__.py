"""Identity queries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetUserQuery:
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class GetUserByEmailQuery:
    email: str


@dataclass(frozen=True, slots=True)
class GetTenantQuery:
    tenant_id: int
