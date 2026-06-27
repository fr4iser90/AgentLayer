"""Repository ports for delegations."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.delegation.entities import DelegationTask
from apps.backend.domain.delegation.value_objects import DelegationId


class DelegationTaskRepository(Protocol):
    def get(self, delegation_id: DelegationId) -> DelegationTask | None: ...

    def list_by_status(self, status: str | None = None) -> list[DelegationTask]: ...

    def save(self, task: DelegationTask) -> DelegationTask: ...
