"""Domain write API — sole source of truth for collection-backed board data."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.collections import db as col_db
from apps.backend.domain.collections.bindings import (
    bindings_for_dashboard,
    collection_slug_for_path,
    is_list_path,
)


class CollectionsServiceDependencies(Protocol):
    def top_level_key(self, data_path: str) -> str: ...

    def delete_collection_items_for_list(self, collection_id: uuid.UUID, list_key: str) -> None: ...


_deps: CollectionsServiceDependencies | None = None


def register_collections_service_dependencies(deps: CollectionsServiceDependencies) -> None:
    global _deps
    _deps = deps


def top_level_key(data_path: str) -> str:
    if _deps is None:
        return (data_path or "").split(".", 1)[0]
    return _deps.top_level_key(data_path)


def resolve_bindings_for_dashboard(ws: dict[str, Any]) -> dict[str, str]:
    did = uuid.UUID(str(ws.get("id")))
    owner = uuid.UUID(str(ws.get("owner_user_id")))
    tid = int(ws.get("tenant_id") or 0)
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    vb = ws.get("view_bindings") if isinstance(ws.get("view_bindings"), dict) else {}
    return bindings_for_dashboard(
        dashboard_id=did,
        ui_layout=ul,
        view_bindings=vb,
        owner_user_id=owner,
        tenant_id=tid,
        template_id=ws.get("template_id"),
    )


def append_items(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    bindings: dict[str, str],
    ui_layout: dict[str, Any] | None,
    list_path: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    slug = collection_slug_for_path(bindings, list_path)
    if not slug:
        return {"ok": False, "error": "no collection binding for list_path"}
    col = col_db.collection_get(owner_user_id, slug)
    if col is None:
        col = col_db.collection_ensure(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            slug=slug,
            title=slug,
        )
    cid = uuid.UUID(str(col["id"]))
    added = col_db.items_append(cid, list_path, rows)
    total = len(col_db.items_list(cid, list_path))
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": slug,
        "list_path": list_path,
        "added_count": len(added),
        "added": added,
        "total_count": total,
    }


def update_item(
    *,
    owner_user_id: uuid.UUID,
    bindings: dict[str, str],
    list_path: str,
    row_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    slug = collection_slug_for_path(bindings, list_path)
    if not slug:
        return {"ok": False, "error": "no collection binding for list_path"}
    col = col_db.collection_get(owner_user_id, slug)
    if not col:
        return {"ok": False, "error": "collection not found"}
    updated = col_db.item_update(uuid.UUID(str(col["id"])), list_path, row_id, patch)
    if updated is None:
        return {"ok": False, "error": "row not found"}
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": slug,
        "list_path": list_path,
        "row_id": row_id,
        "row": updated,
    }


def delete_item(
    *,
    owner_user_id: uuid.UUID,
    bindings: dict[str, str],
    list_path: str,
    row_id: str,
) -> dict[str, Any]:
    slug = collection_slug_for_path(bindings, list_path)
    if not slug:
        return {"ok": False, "error": "no collection binding for list_path"}
    col = col_db.collection_get(owner_user_id, slug)
    if not col:
        return {"ok": False, "error": "collection not found"}
    ok = col_db.item_delete(uuid.UUID(str(col["id"])), list_path, row_id)
    if not ok:
        return {"ok": False, "error": "row not found"}
    return {
        "ok": True,
        "source": "domain",
        "collection_slug": slug,
        "list_path": list_path,
        "row_id": row_id,
    }


def patch_fields(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    bindings: dict[str, str],
    ui_layout: dict[str, Any] | None,
    patches: list[dict[str, Any]],
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    errors: list[str] = []
    by_slug: dict[str, dict[str, Any]] = {}

    for p in patches:
        if not isinstance(p, dict):
            continue
        path = str(p.get("path") or "").strip()
        if not path:
            errors.append("empty path")
            continue
        value = p.get("value")
        slug = collection_slug_for_path(bindings, path)
        if not slug:
            slug = collection_slug_for_path(bindings, top_level_key(path))
        if not slug:
            errors.append(f"no collection for path {path!r}")
            continue
        if slug not in by_slug:
            by_slug[slug] = {}
        if is_list_path(ui_layout, path) and isinstance(value, list):
            # Full list replace at path
            col = col_db.collection_get(owner_user_id, slug)
            if col is None:
                col = col_db.collection_ensure(
                    tenant_id=tenant_id,
                    owner_user_id=owner_user_id,
                    slug=slug,
                    title=slug,
                )
            cid = uuid.UUID(str(col["id"]))
            # naive replace: delete all rows for list_key then append
            # For MVP: store list replace in metadata under __list__ prefix OR append only
            by_slug[slug][f"__list__{path}"] = value
        else:
            by_slug[slug][path] = value
        applied.append({"path": path, "collection_slug": slug})

    for slug, fields in by_slug.items():
        col = col_db.collection_get(owner_user_id, slug)
        if col is None:
            col = col_db.collection_ensure(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                slug=slug,
                title=slug,
            )
        cid = uuid.UUID(str(col["id"]))
        meta_patch: dict[str, Any] = {}
        for k, v in fields.items():
            if k.startswith("__list__"):
                lk = k[len("__list__") :]
                # replace list: delete existing rows - need delete all for list_key
                _replace_list(cid, lk, v if isinstance(v, list) else [])
            else:
                meta_patch[k] = v
        if meta_patch:
            col_db.collection_metadata_patch(owner_user_id, slug, meta_patch)

    if errors and not applied:
        return {"ok": False, "error": "; ".join(errors)}
    return {"ok": True, "source": "domain", "applied": applied, "errors": errors}


def _replace_list(collection_id: uuid.UUID, list_key: str, rows: list[Any]) -> None:
    """Replace all items in a list_key (import / full patch)."""
    lk = (list_key or "items").strip()
    if _deps is not None:
        _deps.delete_collection_items_for_list(collection_id, lk)
    dict_rows = [r for r in rows if isinstance(r, dict)]
    if dict_rows:
        col_db.items_append(collection_id, lk, dict_rows)
