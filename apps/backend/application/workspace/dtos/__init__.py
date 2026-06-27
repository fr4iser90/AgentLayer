"""Workspace DTOs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceDto:
    workspace_id: uuid.UUID
    tenant_id: int
    owner_user_id: uuid.UUID
    name: str
    path: str | None
    verify_required: bool
    verify_command: str | None
