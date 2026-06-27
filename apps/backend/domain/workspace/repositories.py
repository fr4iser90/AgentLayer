"""Repository ports for workspaces."""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.backend.domain.workspace.entities import Workspace
from apps.backend.domain.workspace.value_objects import WorkspaceId


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: WorkspaceId, *, user_id: uuid.UUID) -> Workspace | None: ...

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 100) -> list[Workspace]: ...

    def save(self, workspace: Workspace) -> Workspace: ...
