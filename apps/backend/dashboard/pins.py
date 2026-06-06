"""Pin a remote block onto a target dashboard (adds dashboard_ref)."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.block_ref import render_block_from_dashboard
from apps.backend.dashboard.layout_tree import count_layout_blocks, resolve_blocks_target

MAX_BLOCKS = 64


def _new_ref_id() -> str:
    return f"ref_{uuid.uuid4().hex[:10]}"


def _next_grid_y(blocks: list[Any]) -> int:
    y = 0
    for b in blocks:
        if not isinstance(b, dict):
            continue
        grid = b.get("grid") if isinstance(b.get("grid"), dict) else {}
        bottom = int(grid.get("y") or 0) + int(grid.get("h") or 4)
        y = max(y, bottom)
    return y


def pin_block_to_dashboard(
    user_id: uuid.UUID,
    tenant_id: int,
    target_dashboard_id: uuid.UUID,
    *,
    source_dashboard_id: uuid.UUID,
    source_block_id: str,
    parent_block_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any] | None:
    """Add a dashboard_ref block on target if user can edit target and read source block."""
    access = dashboard_db.dashboard_access_ex(user_id, tenant_id, target_dashboard_id)
    if access.role is None or access.role == "viewer":
        return None
    if access.allowed_block_ids is not None:
        return None

    preview = render_block_from_dashboard(
        user_id, tenant_id, source_dashboard_id, source_block_id
    )
    if not preview:
        return None

    row = dashboard_db.dashboard_get(user_id, tenant_id, target_dashboard_id)
    if not row:
        return None

    ul = deepcopy(row.get("ui_layout") if isinstance(row.get("ui_layout"), dict) else {})
    if count_layout_blocks(ul) >= MAX_BLOCKS:
        return None

    target_blocks, err = resolve_blocks_target(ul, parent_block_id)
    if err or target_blocks is None:
        return None

    src_block = preview.get("block") if isinstance(preview.get("block"), dict) else {}
    src_grid = src_block.get("grid") if isinstance(src_block.get("grid"), dict) else {}
    ref_title = (title or preview.get("source_title") or "Pinned").strip()

    ref_block: dict[str, Any] = {
        "id": _new_ref_id(),
        "type": "dashboard_ref",
        "grid": {
            "x": 0,
            "y": _next_grid_y(target_blocks),
            "w": max(4, min(12, int(src_grid.get("w") or 6))),
            "h": max(3, min(20, int(src_grid.get("h") or 6))),
        },
        "props": {
            "title": ref_title,
            "sourceDashboardId": str(source_dashboard_id),
            "sourceBlockId": source_block_id.strip(),
            "sourceLabel": preview.get("source_title") or "",
        },
    }
    target_blocks.append(ref_block)

    updated = dashboard_db.dashboard_update(
        user_id,
        tenant_id,
        target_dashboard_id,
        ui_layout=ul,
    )
    if not updated:
        return None
    return {
        "ok": True,
        "ref_block_id": ref_block["id"],
        "dashboard": updated,
    }
