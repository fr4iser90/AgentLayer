"""Attachment file-ref helpers and persistence port registry."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from apps.backend.domain.collections.value_objects import FILE_REF_PREFIX, FileRef


class CollectionAttachmentsDbDependencies(Protocol):
    def attachment_get_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> dict[str, Any] | None: ...

    def attachment_delete_with_access(
        self,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: int,
    ) -> str | None: ...


_deps: CollectionAttachmentsDbDependencies | None = None


def register_collection_attachments_db_dependencies(deps: CollectionAttachmentsDbDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> CollectionAttachmentsDbDependencies:
    if _deps is None:
        raise RuntimeError("collection attachments db dependencies not registered")
    return _deps


def parse_file_ref(value: str) -> str | None:
    ref = FileRef.parse(value)
    return ref.file_id if ref is not None else None


def file_ids_in_value(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        fid = parse_file_ref(obj)
        if fid:
            out.add(fid)
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= file_ids_in_value(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= file_ids_in_value(v)
    return out


def _row(r: dict[str, Any]) -> dict[str, Any]:
    ca = r.get("created_at")
    return {
        "id": str(r.get("id") or ""),
        "owner_user_id": str(r.get("owner_user_id") or ""),
        "collection_id": str(r["collection_id"]) if r.get("collection_id") else None,
        "storage_relpath": r.get("storage_relpath") or "",
        "content_type": r.get("content_type") or "",
        "size_bytes": int(r.get("size_bytes") or 0),
        "original_name": r.get("original_name") or "",
        "created_at": ca.isoformat() if isinstance(ca, datetime) else str(ca or ""),
    }


def attachment_get_with_access(
    file_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> dict[str, Any] | None:
    """Owner, collection share grantee, or dashboard member (bound collection) may read."""
    return _require_deps().attachment_get_with_access(file_id, user_id, tenant_id)


def attachment_delete_with_access(
    file_id: uuid.UUID, user_id: uuid.UUID, tenant_id: int
) -> str | None:
    """Only the attachment owner may delete."""
    return _require_deps().attachment_delete_with_access(file_id, user_id, tenant_id)
