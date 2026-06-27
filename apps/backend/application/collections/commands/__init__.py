"""Collection write commands."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EnsureCollectionCommand:
    tenant_id: int
    owner_user_id: uuid.UUID
    slug: str
    title: str = ""
    schema_hint: str | None = None


@dataclass(frozen=True, slots=True)
class PatchCollectionMetadataCommand:
    owner_user_id: uuid.UUID
    slug: str
    patch: dict[str, Any] = field(default_factory=dict)
