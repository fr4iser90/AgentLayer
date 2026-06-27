"""Repository ports for the collections bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.collections.entities import Attachment, Collection, CollectionItem
from apps.backend.domain.collections.value_objects import CollectionSlug, DataPath


class CollectionRepository(Protocol):
    def ensure(
        self,
        *,
        tenant_id: int,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
        title: str = "",
        schema_hint: str | None = None,
    ) -> Collection: ...

    def get_by_slug(
        self,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
    ) -> Collection | None: ...

    def list_for_owner(self, owner_user_id: uuid.UUID, *, limit: int = 100) -> list[Collection]: ...

    def patch_metadata(
        self,
        owner_user_id: uuid.UUID,
        slug: CollectionSlug,
        patch: dict[str, Any],
    ) -> Collection | None: ...


class CollectionItemRepository(Protocol):
    def list_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        *,
        limit: int = 2000,
    ) -> list[CollectionItem]: ...

    def append_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        rows: list[dict[str, Any]],
    ) -> list[CollectionItem]: ...

    def update_item(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        row_id: str,
        patch: dict[str, Any],
    ) -> CollectionItem | None: ...

    def delete_item(self, collection_id: uuid.UUID, list_key: DataPath, row_id: str) -> bool: ...

    def replace_items(
        self,
        collection_id: uuid.UUID,
        list_key: DataPath,
        rows: list[dict[str, Any]],
    ) -> None: ...


class AttachmentRepository(Protocol):
    def insert_upload(
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

    def get_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> Attachment | None: ...

    def delete_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> str | None: ...
