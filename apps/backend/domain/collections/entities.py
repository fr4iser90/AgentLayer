"""Entities for the collections bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.backend.domain.collections.value_objects import CollectionSlug, DataPath, FileRef


@dataclass(slots=True)
class CollectionItem:
    row_id: str
    list_key: DataPath
    data: dict[str, Any]
    sort_order: int | None = None

    @classmethod
    def from_row_data(
        cls,
        data: dict[str, Any],
        *,
        list_key: str,
        sort_order: int | None = None,
    ) -> "CollectionItem":
        body = dict(data)
        row_id = str(body.get("id") or "").strip() or f"r_{uuid.uuid4().hex[:12]}"
        body["id"] = row_id
        parsed_path = DataPath.parse(list_key) or DataPath("items")
        return cls(row_id=row_id, list_key=parsed_path, data=body, sort_order=sort_order)


@dataclass(slots=True)
class Collection:
    id: uuid.UUID | None
    tenant_id: int
    owner_user_id: uuid.UUID
    slug: CollectionSlug
    title: str
    schema_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def patch_metadata(self, patch: dict[str, Any]) -> None:
        self.metadata.update({str(k): v for k, v in patch.items() if str(k).strip()})


@dataclass(frozen=True, slots=True)
class Attachment:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    storage_relpath: str
    content_type: str
    size_bytes: int
    original_name: str
    collection_id: uuid.UUID | None = None
    file_ref: FileRef | None = None
