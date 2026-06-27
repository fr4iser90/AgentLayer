"""Map dashboard dataPath → domain collection slug (view bindings)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from apps.backend.domain.collections import db as col_db


class CollectionsViewDependencies(Protocol):
    def top_level_key(self, data_path: str) -> str: ...

    def iter_layout_blocks(self, ui_layout: dict[str, Any] | None) -> list[dict[str, Any]]: ...

    def data_paths_from_blocks(self, blocks: list[Any]) -> list[str]: ...


_view_deps: CollectionsViewDependencies | None = None


def register_collections_view_dependencies(deps: CollectionsViewDependencies) -> None:
    global _view_deps
    _view_deps = deps


def top_level_key(data_path: str) -> str:
    if _view_deps is None:
        return (data_path or "").split(".", 1)[0]
    return _view_deps.top_level_key(data_path)


def iter_layout_blocks(ui_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if _view_deps is None:
        blocks = ui_layout.get("blocks") if isinstance(ui_layout, dict) else []
        return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []
    return list(_view_deps.iter_layout_blocks(ui_layout))


def data_paths_from_blocks(blocks: list[Any]) -> list[str]:
    if _view_deps is None:
        out: list[str] = []
        for block in blocks:
            props = block.get("props") if isinstance(block, dict) and isinstance(block.get("props"), dict) else {}
            dp = str(props.get("dataPath") or "").strip()
            if dp:
                out.append(dp)
        return out
    return list(_view_deps.data_paths_from_blocks(blocks))


def default_collection_slug_for_path(data_path: str) -> str:
    """Top-level list paths use their name as slug; nested paths use dotted slug."""
    dp = (data_path or "").strip()
    if not dp:
        return "items"
    return dp.replace(" ", "_").lower()


def parse_view_bindings(raw: Any) -> dict[str, str]:
    """``{dataPath: collection_slug}`` from dashboard row."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        path = str(k or "").strip()
        if not path:
            continue
        if isinstance(v, str):
            slug = v.strip()
        elif isinstance(v, dict):
            slug = str(v.get("collection_slug") or v.get("slug") or "").strip()
        else:
            continue
        if slug and col_db.normalize_slug(slug):
            out[path] = slug
    return out


def bindings_for_dashboard(
    *,
    dashboard_id: uuid.UUID,
    ui_layout: dict[str, Any] | None,
    view_bindings: dict[str, Any] | None,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    template_id: str | None = None,
) -> dict[str, str]:
    """
    Resolve dataPath → collection slug.
    Explicit view_bindings win; else props.collectionSlug on block; else default slug per path.
    """
    explicit = parse_view_bindings(view_bindings)
    out: dict[str, str] = dict(explicit)

    for block in iter_layout_blocks(ui_layout if isinstance(ui_layout, dict) else None):
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        dp = str(props.get("dataPath") or "").strip()
        if not dp:
            continue
        if dp in out:
            continue
        cslug = str(props.get("collectionSlug") or "").strip()
        if cslug and col_db.normalize_slug(cslug):
            out[dp] = cslug
            continue
        # Default: one collection per dashboard + path for isolation
        out[dp] = f"d{str(dashboard_id).replace('-', '')[:12]}-{default_collection_slug_for_path(dp)}"

    # Ensure collections exist for discovered bindings
    for path, slug in list(out.items()):
        hint = (template_id or "").strip() or None
        col_db.collection_ensure(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            slug=slug,
            title=slug,
            schema_hint=hint,
        )
    return out


def collection_slug_for_path(
    bindings: dict[str, str],
    data_path: str,
) -> str | None:
    dp = (data_path or "").strip()
    if not dp:
        return None
    if dp in bindings:
        return bindings[dp]
    top = top_level_key(dp)
    if top in bindings:
        return bindings[top]
    return bindings.get(dp)


def is_list_path(ui_layout: dict[str, Any] | None, data_path: str) -> bool:
    dp = (data_path or "").strip()
    for block in iter_layout_blocks(ui_layout if isinstance(ui_layout, dict) else None):
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        if str(props.get("dataPath") or "").strip() != dp:
            continue
        btype = str(block.get("type") or "").strip().lower()
        return btype in ("table", "card_grid", "gallery", "list")
    # Heuristic: dotted path ending in known list segment
    return dp.endswith(".photos") or dp in data_paths_from_blocks(
        (ui_layout or {}).get("blocks") if isinstance(ui_layout, dict) else []
    )
