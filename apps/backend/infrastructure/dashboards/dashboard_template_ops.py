"""Export / import dashboard layout snapshots (no live sync)."""

from __future__ import annotations

import copy
from typing import Any

from apps.backend.infrastructure.dashboards.dashboard_layout_tree import count_layout_blocks, flatten_block_ids

MAX_EXPORT_BLOCKS = 64
_RESERVED_DATA_PREFIX = "_agentlayer"


def _strip_agentlayer_meta(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not str(k).startswith(_RESERVED_DATA_PREFIX)}


def export_template_payload(
    *,
    kind: str,
    title: str,
    ui_layout: dict[str, Any],
    data: dict[str, Any],
    template_id: str | None = None,
) -> dict[str, Any]:
    """Anonymized layout snippet suitable for from-template import."""
    ul = copy.deepcopy(ui_layout) if isinstance(ui_layout, dict) else {"version": 1, "blocks": []}
    dt = _strip_agentlayer_meta(copy.deepcopy(data) if isinstance(data, dict) else {})
    out: dict[str, Any] = {
        "kind": (kind or "custom").strip() or "custom",
        "title": (title or "").strip() or "Dashboard",
        "ui_layout": ul,
        "initial_data": dt,
        "block_count": count_layout_blocks(ul),
    }
    tid = (template_id or "").strip()
    if tid:
        out["template_id"] = tid
    return out


def validate_template_import(
    *,
    kind: str,
    template_id: str | None = None,
    ui_layout: dict[str, Any] | None,
    data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    _ = kind, template_id
    if not isinstance(ui_layout, dict):
        return {}, {}, "ui_layout must be an object"
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, list):
        return {}, {}, "ui_layout.blocks must be a list"
    if count_layout_blocks(ui_layout) > MAX_EXPORT_BLOCKS:
        return {}, {}, f"layout exceeds {MAX_EXPORT_BLOCKS} blocks"
    ids = flatten_block_ids(ui_layout)
    if len(ids) != len(set(ids)):
        return {}, {}, "duplicate block ids in layout"
    for bid in ids:
        if not bid or len(bid) > 120:
            return {}, {}, "invalid block id in layout"
    dt = data if isinstance(data, dict) else {}
    clean_data = _strip_agentlayer_meta(dt)
    return ui_layout, clean_data, None
