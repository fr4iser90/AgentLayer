"""Workspace write commands."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SaveWorkspaceCommand:
    workspace_id: uuid.UUID
    tenant_id: int
    owner_user_id: uuid.UUID
    name: str
    path: str | None = None
    verify_required: bool = False
    verify_command: str | None = None
