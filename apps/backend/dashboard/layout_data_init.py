"""Initialize missing dashboard data keys when applying a new ui_layout."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from apps.backend.dashboard.layout_tree import data_paths_from_blocks


def _default_data_for_block(block_type: str, data_path: str) -> dict[str, Any]:
    if block_type == "table":
        return {data_path: []}
    if block_type in ("markdown", "rich_markdown"):
        return {data_path: ""}
    if block_type == "gallery":
        return {data_path: []}
    if block_type == "hero":
        return {data_path: {"url": "", "caption": "", "headline": ""}}
    if block_type == "timeline":
        return {data_path: {"events": []}}
    if block_type == "stat":
        return {data_path: {"label": "KPI", "value": 0}}
    if block_type == "chart":
        return {
            data_path: {
                "chartType": "line",
                "labels": ["A", "B", "C"],
                "series": [{"label": "Serie 1", "data": [0, 0, 0]}],
            }
        }
    if block_type == "sparkline":
        return {data_path: {"values": [0, 0, 0, 0]}}
    if block_type == "kanban":
        return {
            data_path: {
                "columns": [
                    {"id": "todo", "title": "Todo", "cards": []},
                    {"id": "done", "title": "Done", "cards": []},
                ]
            }
        }
    if block_type == "embed":
        return {data_path: {"url": "", "title": ""}}
    if block_type == "card_grid":
        return {data_path: []}
    return {}


def _init_data_from_blocks(blocks: list[Any], data: dict[str, Any]) -> None:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = str(b.get("type") or "").strip().lower()
        props = b.get("props") if isinstance(b.get("props"), dict) else {}
        dp = str(props.get("dataPath") or "").strip()
        if dp and dp not in data:
            for k, v in _default_data_for_block(btype, dp).items():
                data.setdefault(k, copy.deepcopy(v))
        if btype == "section":
            nested = props.get("nested")
            if isinstance(nested, dict):
                nb = nested.get("blocks")
                if isinstance(nb, list):
                    _init_data_from_blocks(nb, data)


def merge_data_for_layout(
    current_data: dict[str, Any] | None,
    ui_layout: dict[str, Any],
) -> dict[str, Any]:
    """Keep existing data; add defaults for new block data paths in ``ui_layout``."""
    base = copy.deepcopy(current_data) if isinstance(current_data, dict) else {}
    blocks = ui_layout.get("blocks") if isinstance(ui_layout.get("blocks"), list) else []
    _init_data_from_blocks(blocks, base)
    # Ensure every declared path has at least an empty placeholder
    for dp in data_paths_from_blocks(blocks):
        top = dp.split(".", 1)[0]
        if top and top not in base:
            base[top] = []
    return base


def new_proposal_id() -> str:
    return f"prop_{uuid.uuid4().hex[:10]}"


def new_proposal_set_id() -> str:
    return f"pset_{uuid.uuid4().hex[:12]}"
