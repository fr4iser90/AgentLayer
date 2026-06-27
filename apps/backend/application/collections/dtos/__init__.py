"""Collection DTOs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CollectionDto:
    collection_id: uuid.UUID | None
    tenant_id: int
    owner_user_id: uuid.UUID
    slug: str
    title: str
    schema_hint: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
