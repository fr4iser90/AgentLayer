"""Row mapping for Postgres collection persistence."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.backend.domain.collections.entities import Collection
from apps.backend.domain.collections.value_objects import CollectionSlug


def uuid_or_none(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def datetime_or_none(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def collection_from_row(row: dict[str, Any] | None) -> Collection | None:
    if not row:
        return None
    slug = CollectionSlug.parse(str(row.get("slug") or ""))
    owner = uuid_or_none(row.get("owner_user_id"))
    if slug is None or owner is None:
        return None
    return Collection(
        id=uuid_or_none(row.get("id")),
        tenant_id=int(row.get("tenant_id") or 0),
        owner_user_id=owner,
        slug=slug,
        title=str(row.get("title") or str(slug)),
        schema_hint=row.get("schema_hint") if isinstance(row.get("schema_hint"), str) else None,
        metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        created_at=datetime_or_none(row.get("created_at")),
        updated_at=datetime_or_none(row.get("updated_at")),
    )


def collection_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": str(row["id"]),
        "tenant_id": int(row.get("tenant_id") or 0),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "slug": row["slug"],
        "title": row.get("title") or "",
        "schema_hint": row.get("schema_hint"),
        "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        "created_at": row["created_at"].isoformat() if isinstance(row.get("created_at"), datetime) else None,
        "updated_at": row["updated_at"].isoformat() if isinstance(row.get("updated_at"), datetime) else None,
    }


def attachment_row(row: dict[str, Any]) -> dict[str, Any]:
    created_at = row.get("created_at")
    return {
        "id": str(row.get("id") or ""),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "collection_id": str(row["collection_id"]) if row.get("collection_id") else None,
        "storage_relpath": row.get("storage_relpath") or "",
        "content_type": row.get("content_type") or "",
        "size_bytes": int(row.get("size_bytes") or 0),
        "original_name": row.get("original_name") or "",
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or ""),
    }
