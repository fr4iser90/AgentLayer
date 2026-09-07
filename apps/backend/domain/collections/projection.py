"""Project domain collections into dashboard ``data`` shape (view layer only)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.collections import db as col_db
from apps.backend.domain.collections.bindings import (
    RESERVED_DATA_KEYS,
    bindings_for_dashboard,
    is_list_path,
)


class CollectionsProjectionDependencies(Protocol):
    def get_path(self, data: dict[str, Any], data_path: str) -> Any: ...

    def set_path(self, data: dict[str, Any], data_path: str, value: Any) -> dict[str, Any]: ...

    def iter_layout_blocks(self, ui_layout: dict[str, Any] | None) -> list[dict[str, Any]]: ...

    def finalize_dashboard_data(
        self,
        data: dict[str, Any],
        ui_layout: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


_deps: CollectionsProjectionDependencies | None = None


def register_collections_projection_dependencies(deps: CollectionsProjectionDependencies) -> None:
    global _deps
    _deps = deps


def get_path(data: dict[str, Any], data_path: str) -> Any:
    if _deps is None:
        cur: Any = data
        for part in (data_path or "").split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    return _deps.get_path(data, data_path)


def set_path(data: dict[str, Any], data_path: str, value: Any) -> dict[str, Any]:
    if _deps is None:
        out = dict(data)
        cur = out
        parts = [p for p in (data_path or "").split(".") if p]
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        if parts:
            cur[parts[-1]] = value
        return out
    return _deps.set_path(data, data_path, value)


def iter_layout_blocks(ui_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if _deps is None:
        blocks = ui_layout.get("blocks") if isinstance(ui_layout, dict) else []
        return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []
    return list(_deps.iter_layout_blocks(ui_layout))


def finalize_dashboard_data(data: dict[str, Any], ui_layout: dict[str, Any] | None) -> dict[str, Any]:
    return _deps.finalize_dashboard_data(data, ui_layout) if _deps is not None else data


#: Collection metadata keys with this prefix are bookkeeping, never projected into ``data``.
_INTERNAL_META_PREFIX = "__"


def _is_internal_meta_key(key: str) -> bool:
    return key.startswith(_INTERNAL_META_PREFIX)


def _legacy_import_marker(path: str) -> str:
    return f"{_INTERNAL_META_PREFIX}legacy_import__{path}"


def _metadata_to_data_paths(metadata: dict[str, Any], ui_layout: dict[str, Any] | None) -> dict[str, Any]:
    """Apply metadata keys that match block dataPaths (scalars / markdown)."""
    data: dict[str, Any] = {}
    if not isinstance(metadata, dict):
        return data
    paths: set[str] = set()
    for block in iter_layout_blocks(ui_layout):
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        dp = str(props.get("dataPath") or "").strip()
        if dp:
            paths.add(dp)
    for key, val in metadata.items():
        k = str(key).strip()
        if not k:
            continue
        if k in paths or "." not in k:
            data = set_path(data, k, val)
    return data


def project_dashboard_data(
    *,
    dashboard_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    ui_layout: dict[str, Any] | None,
    view_bindings: dict[str, Any] | None,
    template_id: str | None,
    legacy_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ``data`` dict from domain collections (source of truth)."""
    bindings = bindings_for_dashboard(
        dashboard_id=dashboard_id,
        ui_layout=ui_layout,
        view_bindings=view_bindings,
        owner_user_id=owner_user_id,
        tenant_id=tenant_id,
        template_id=template_id,
    )
    data: dict[str, Any] = {}

    # Metadata fields per collection (merge by path prefix)
    seen_slugs: set[str] = set()
    for path, slug in bindings.items():
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        col = col_db.collection_get(owner_user_id, slug)
        if not col:
            continue
        meta = col.get("metadata") if isinstance(col.get("metadata"), dict) else {}
        for mk, mv in meta.items():
            mp = str(mk).strip()
            if mp and not _is_internal_meta_key(mp):
                data = set_path(data, mp, mv)

    # List paths from bindings
    for path, slug in bindings.items():
        if not is_list_path(ui_layout, path):
            continue
        col = col_db.collection_get(owner_user_id, slug)
        if not col:
            continue
        cid = uuid.UUID(str(col["id"]))
        rows = col_db.items_list(cid, path)
        data = set_path(data, path, rows)

    # Dashboard-level config is not bound to a block dataPath and stays in the row.
    if isinstance(legacy_data, dict):
        for key in RESERVED_DATA_KEYS:
            if key in legacy_data:
                data[key] = legacy_data[key]

    # Legacy one-time import: if domain empty but legacy JSON had content
    if legacy_data and isinstance(legacy_data, dict):
        _maybe_import_legacy(
            owner_user_id=owner_user_id,
            tenant_id=tenant_id,
            bindings=bindings,
            ui_layout=ui_layout,
            legacy_data=legacy_data,
            projected=data,
        )
        # Re-project after import
        for path, slug in bindings.items():
            if is_list_path(ui_layout, path):
                col = col_db.collection_get(owner_user_id, slug)
                if col:
                    rows = col_db.items_list(uuid.UUID(str(col["id"])), path)
                    data = set_path(data, path, rows)
            col = col_db.collection_get(owner_user_id, slug)
            if col:
                meta = col.get("metadata") if isinstance(col.get("metadata"), dict) else {}
                for mk, mv in meta.items():
                    mp = str(mk).strip()
                    if mp and not _is_internal_meta_key(mp) and get_path(data, mp) is None:
                        data = set_path(data, mp, mv)

    return finalize_dashboard_data(data, ui_layout if isinstance(ui_layout, dict) else None)


def _maybe_import_legacy(
    *,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    bindings: dict[str, str],
    ui_layout: dict[str, Any] | None,
    legacy_data: dict[str, Any],
    projected: dict[str, Any],
) -> None:
    for path, slug in bindings.items():
        col = col_db.collection_get(owner_user_id, slug)
        if not col:
            col = col_db.collection_ensure(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                slug=slug,
                title=slug,
            )
        cid = uuid.UUID(str(col["id"]))
        if is_list_path(ui_layout, path):
            meta = col.get("metadata") if isinstance(col.get("metadata"), dict) else {}
            marker = _legacy_import_marker(path)
            if meta.get(marker):
                # Already migrated — an emptied list must stay empty, not resurrect the seed.
                continue
            existing = col_db.items_list(cid, path, limit=1)
            if not existing:
                raw = get_path(legacy_data, path)
                if isinstance(raw, list) and raw:
                    col_db.items_append(cid, path, [r for r in raw if isinstance(r, dict)])
            col_db.collection_metadata_patch(owner_user_id, slug, {marker: True})
        else:
            meta = col.get("metadata") if isinstance(col.get("metadata"), dict) else {}
            if path in meta:
                continue
            val = get_path(legacy_data, path)
            if val is not None:
                col_db.collection_metadata_patch(owner_user_id, slug, {path: val})
