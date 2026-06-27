"""Collection read queries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetCollectionBySlugQuery:
    owner_user_id: uuid.UUID
    slug: str


@dataclass(frozen=True, slots=True)
class ListCollectionsQuery:
    owner_user_id: uuid.UUID
    limit: int = 100
