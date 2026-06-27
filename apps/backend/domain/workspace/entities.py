"""Workspace entities."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.backend.domain.workspace.value_objects import WorkspaceId, WorkspaceName


@dataclass(slots=True)
class Workspace:
    id: WorkspaceId
    tenant_id: int
    owner_user_id: uuid.UUID
    name: WorkspaceName
    path: str | None = None
    verify_required: bool = False
    verify_command: str | None = None

    def __post_init__(self) -> None:
        if self.tenant_id <= 0:
            raise ValueError("tenant_id must be positive")
        if self.path is not None and not self.path.strip():
            raise ValueError("workspace path must not be blank")

    def can_finish_without_verify(self) -> bool:
        return not self.verify_required
