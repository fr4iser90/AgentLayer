"""Workspace value objects."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceId:
    value: uuid.UUID

    @classmethod
    def parse(cls, raw: str | uuid.UUID) -> "WorkspaceId":
        return cls(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))


@dataclass(frozen=True, slots=True)
class WorkspaceName:
    value: str

    @classmethod
    def parse(cls, raw: str | None) -> "WorkspaceName":
        value = (raw or "").strip()
        if not value or len(value) > 200:
            raise ValueError("workspace name must be 1..200 characters")
        return cls(value)
