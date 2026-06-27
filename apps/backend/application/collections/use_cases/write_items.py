"""Write use cases for collection-backed dashboard data."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.application.collections.ports import CollectionItemRepository, CollectionRepository
from apps.backend.domain.collections.bindings import collection_slug_for_path, is_list_path
from apps.backend.domain.collections.value_objects import CollectionSlug, DataPath


def _slug_for_path(bindings: dict[str, str], path: str) -> CollectionSlug | None:
    raw = collection_slug_for_path(bindings, path)
    return CollectionSlug.parse(raw or "")


def _ensure_collection(
    collections: CollectionRepository,
    *,
    tenant_id: int,
    owner_user_id: uuid.UUID,
    slug: CollectionSlug,
) -> uuid.UUID:
    collection = collections.get_by_slug(owner_user_id, slug)
    if collection is None:
        collection = collections.ensure(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            slug=slug,
            title=str(slug),
        )
    if collection.id is None:
        raise RuntimeError("collection repository returned collection without id")
    return collection.id


def append_items(
    *,
    collections: CollectionRepository,
    items: CollectionItemRepository,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    bindings: dict[str, str],
    list_path: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    slug = _slug_for_path(bindings, list_path)
    if slug is None:
        return {"ok": False, "error": "no collection binding for list_path"}
    list_key = DataPath.parse(list_path)
    if list_key is None:
        return {"ok": False, "error": "empty list_path"}
    collection_id = _ensure_collection(
        collections,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        slug=slug,
    )
    added = items.append_items(collection_id, list_key, rows)
    total = len(items.list_items(collection_id, list_key))
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": str(slug),
        "list_path": str(list_key),
        "added_count": len(added),
        "added": [item.data for item in added],
        "total_count": total,
    }


def update_item(
    *,
    collections: CollectionRepository,
    items: CollectionItemRepository,
    owner_user_id: uuid.UUID,
    bindings: dict[str, str],
    list_path: str,
    row_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    slug = _slug_for_path(bindings, list_path)
    if slug is None:
        return {"ok": False, "error": "no collection binding for list_path"}
    list_key = DataPath.parse(list_path)
    if list_key is None:
        return {"ok": False, "error": "empty list_path"}
    collection = collections.get_by_slug(owner_user_id, slug)
    if collection is None or collection.id is None:
        return {"ok": False, "error": "collection not found"}
    updated = items.update_item(collection.id, list_key, row_id, patch)
    if updated is None:
        return {"ok": False, "error": "row not found"}
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": str(slug),
        "list_path": str(list_key),
        "row_id": row_id,
        "row": updated.data,
    }


def delete_item(
    *,
    collections: CollectionRepository,
    items: CollectionItemRepository,
    owner_user_id: uuid.UUID,
    bindings: dict[str, str],
    list_path: str,
    row_id: str,
) -> dict[str, Any]:
    slug = _slug_for_path(bindings, list_path)
    if slug is None:
        return {"ok": False, "error": "no collection binding for list_path"}
    list_key = DataPath.parse(list_path)
    if list_key is None:
        return {"ok": False, "error": "empty list_path"}
    collection = collections.get_by_slug(owner_user_id, slug)
    if collection is None or collection.id is None:
        return {"ok": False, "error": "collection not found"}
    ok = items.delete_item(collection.id, list_key, row_id)
    if not ok:
        return {"ok": False, "error": "row not found"}
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": str(slug),
        "list_path": str(list_key),
        "row_id": row_id,
    }


def patch_fields(
    *,
    collections: CollectionRepository,
    items: CollectionItemRepository,
    top_level_key: Any,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    bindings: dict[str, str],
    ui_layout: dict[str, Any] | None,
    patches: list[dict[str, Any]],
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    errors: list[str] = []
    by_slug: dict[CollectionSlug, dict[str, Any]] = {}

    for patch in patches:
        if not isinstance(patch, dict):
            continue
        path = str(patch.get("path") or "").strip()
        if not path:
            errors.append("empty path")
            continue
        slug = _slug_for_path(bindings, path)
        if slug is None:
            slug = _slug_for_path(bindings, top_level_key(path))
        if slug is None:
            errors.append(f"no collection for path {path!r}")
            continue
        by_slug.setdefault(slug, {})
        value = patch.get("value")
        if is_list_path(ui_layout, path) and isinstance(value, list):
            by_slug[slug][f"__list__{path}"] = value
        else:
            by_slug[slug][path] = value
        applied.append({"path": path, "collection_slug": str(slug)})

    for slug, fields in by_slug.items():
        collection_id = _ensure_collection(
            collections,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            slug=slug,
        )
        meta_patch: dict[str, Any] = {}
        for key, value in fields.items():
            if key.startswith("__list__"):
                list_key_raw = key[len("__list__") :]
                list_key = DataPath.parse(list_key_raw) or DataPath("items")
                rows = value if isinstance(value, list) else []
                items.replace_items(collection_id, list_key, [r for r in rows if isinstance(r, dict)])
            else:
                meta_patch[key] = value
        if meta_patch:
            collections.patch_metadata(owner_user_id, slug, meta_patch)

    if errors and not applied:
        return {"ok": False, "error": "; ".join(errors)}
    return {"ok": True, "source": "domain", "applied": applied, "errors": errors}
