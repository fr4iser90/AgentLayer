"""Repository ports for identity."""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.backend.domain.identity.entities import Tenant, User
from apps.backend.domain.identity.value_objects import EmailAddress, TenantId


class UserRepository(Protocol):
    def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    def get_by_email(self, email: EmailAddress) -> User | None: ...

    def list_by_tenant(self, tenant_id: TenantId, *, limit: int = 100) -> list[User]: ...

    def save(self, user: User) -> User: ...


class TenantRepository(Protocol):
    def get(self, tenant_id: TenantId) -> Tenant | None: ...

    def default(self) -> Tenant: ...
