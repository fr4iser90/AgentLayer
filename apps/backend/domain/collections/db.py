"""Collection persistence port registry for the collections bounded context."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from apps.backend.domain.collections.value_objects import CollectionSlug

class CollectionsDbDependencies(Protocol):
    def collection_ensure(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        slug: str,
        title: str = "",
        schema_hint: str | None = None,
    ) -> dict[str, Any]: ...

    def collection_get(self, owner_user_id: uuid.UUID, slug: str) -> dict[str, Any] | None: ...

    def collection_get_by_id(self, collection_id: uuid.UUID) -> dict[str, Any] | None: ...

    def collection_list(self, owner_user_id: uuid.UUID, *, limit: int = 100) -> list[dict[str, Any]]: ...

    def collection_metadata_patch(
        self,
        owner_user_id: uuid.UUID,
        slug: str,
        patches: dict[str, Any],
    ) -> dict[str, Any] | None: ...

    def items_list(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        *,
        limit: int = 2000,
    ) -> list[dict[str, Any]]: ...

    def items_append(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        rows: list[dict[str, Any]],
        *,
        start_sort: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def item_update(
        self,
        collection_id: uuid.UUID,
        list_key: str,
        row_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any] | None: ...

    def item_delete(self, collection_id: uuid.UUID, list_key: str, row_id: str) -> bool: ...

    def attachment_insert(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        storage_relpath: str,
        content_type: str,
        size_bytes: int,
        original_name: str,
        collection_id: uuid.UUID | None = None,
        collection_item_id: uuid.UUID | None = None,
        dashboard_id: uuid.UUID | None = None,
    ) -> dict[str, Any]: ...


_deps: CollectionsDbDependencies | None = None


def register_collections_db_dependencies(deps: CollectionsDbDependencies) -> None:
    global _deps
    _deps = deps


def normalize_slug(raw: str) -> str | None:
    slug = CollectionSlug.parse(raw)
    return str(slug) if slug is not None else None


def _require_deps() -> CollectionsDbDependencies:
    if _deps is None:
        raise RuntimeError("collections db dependencies not registered")
    return _deps


def collection_ensure(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    slug: str,
    title: str = "",
    schema_hint: str | None = None,
) -> dict[str, Any]:
    norm = normalize_slug(slug)
    if norm is None:
        raise ValueError("invalid collection slug")
    return _require_deps().collection_ensure(
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        slug=norm,
        title=title,
        schema_hint=schema_hint,
    )


def collection_get(
    owner_user_id: uuid.UUID,
    slug: str,
) -> dict[str, Any] | None:
    norm = normalize_slug(slug)
    if norm is None:
        return None
    return _require_deps().collection_get(owner_user_id, norm)


def collection_get_by_id(collection_id: uuid.UUID) -> dict[str, Any] | None:
    return _require_deps().collection_get_by_id(collection_id)


def collection_list(owner_user_id: uuid.UUID, *, limit: int = 100) -> list[dict[str, Any]]:
    return _require_deps().collection_list(owner_user_id, limit=limit)


def collection_metadata_patch(
    owner_user_id: uuid.UUID,
    slug: str,
    patches: dict[str, Any],
) -> dict[str, Any] | None:
    norm = normalize_slug(slug)
    if norm is None:
        return None
    return _require_deps().collection_metadata_patch(owner_user_id, norm, patches)


def items_list(
    collection_id: uuid.UUID,
    list_key: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    return _require_deps().items_list(collection_id, list_key, limit=limit)


def items_append(
    collection_id: uuid.UUID,
    list_key: str,
    rows: list[dict[str, Any]],
    *,
    start_sort: int | None = None,
) -> list[dict[str, Any]]:
    return _require_deps().items_append(
        collection_id,
        list_key,
        rows,
        start_sort=start_sort,
    )


def item_update(
    collection_id: uuid.UUID,
    list_key: str,
    row_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    return _require_deps().item_update(collection_id, list_key, row_id, patch)


def item_delete(collection_id: uuid.UUID, list_key: str, row_id: str) -> bool:
    return _require_deps().item_delete(collection_id, list_key, row_id)


def attachment_insert(
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    storage_relpath: str,
    content_type: str,
    size_bytes: int,
    original_name: str,
    collection_id: uuid.UUID | None = None,
    collection_item_id: uuid.UUID | None = None,
    dashboard_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return _require_deps().attachment_insert(
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        storage_relpath=storage_relpath,
        content_type=content_type,
        size_bytes=size_bytes,
        original_name=original_name,
        collection_id=collection_id,
        collection_item_id=collection_item_id,
        dashboard_id=dashboard_id,
    )


def _collection_row(row: dict[str, Any] | None) -> dict[str, Any]:
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
