"""Resolve a single block (+ data slice) from a source dashboard with ACL checks."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.dashboards import dashboard_db
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import (
    data_paths_from_blocks,
    find_block_by_id,
    normalize_nested_layout,
)


def _data_slice_for_block(data: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(block, dict):
        return {}
    paths = data_paths_from_blocks([block])
    keys: set[str] = set()
    for p in paths:
        if p:
            keys.add(p.split(".")[0])
    if str(block.get("type") or "").strip().lower() == "section":
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        nested = normalize_nested_layout(props.get("nested"))
        for p in data_paths_from_blocks(nested.get("blocks") or []):
            if p:
                keys.add(p.split(".")[0])
    if not keys:
        return {}
    return {k: data[k] for k in keys if k in data}


def _load_source_row(
    tenant_id: int,
    source_dashboard_id: uuid.UUID,
) -> tuple[dict[str, Any], dict[str, Any], str, str] | None:
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ui_layout, data, title, kind
                FROM user_dashboards
                WHERE id = %s AND tenant_id = %s
                """,
                (source_dashboard_id, tenant_id),
            )
            raw = cur.fetchone()
        conn.commit()
    if not raw:
        return None
    ul = raw[0] if isinstance(raw[0], dict) else {}
    dt = raw[1] if isinstance(raw[1], dict) else {}
    return ul, dt, str(raw[2] or ""), str(raw[3] or "custom")


def render_block_from_dashboard(
    user_id: uuid.UUID,
    tenant_id: int,
    source_dashboard_id: uuid.UUID,
    block_id: str,
) -> dict[str, Any] | None:
    """Return block definition + data slice if the user may read the source block."""
    bid = (block_id or "").strip()
    if not bid:
        return None

    access = dashboard_db.dashboard_access_ex(user_id, tenant_id, source_dashboard_id)
    if access.role is None:
        return None
    if access.allowed_block_ids is not None and bid not in access.allowed_block_ids:
        return None

    loaded = _load_source_row(tenant_id, source_dashboard_id)
    if not loaded:
        return None
    ul, full_data, title, kind = loaded

    block = find_block_by_id(ul, bid)
    if not block:
        return None

    if access.allowed_block_ids is not None:
        from apps.backend.infrastructure.dashboards.dashboard_granular_update_db import (
            _filter_data_for_visible_blocks,
            _filter_ui_layout,
        )

        filtered = _filter_ui_layout(ul, access.allowed_block_ids)
        if not find_block_by_id(filtered, bid):
            return None
        filtered_ul = {"blocks": [block]}
        data_slice = _filter_data_for_visible_blocks(full_data, filtered_ul)
    else:
        data_slice = _data_slice_for_block(full_data, block)

    return {
        "source_dashboard_id": str(source_dashboard_id),
        "source_block_id": bid,
        "source_title": title,
        "source_kind": kind,
        "block": block,
        "data": data_slice,
    }
