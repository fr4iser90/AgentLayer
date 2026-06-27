"""Workspace read queries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetWorkspaceQuery:
    workspace_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ListWorkspacesQuery:
    user_id: uuid.UUID
    limit: int = 100
