"""Schema validation for dashboard layout and data JSON."""
from __future__ import annotations

from typing import Any

_MAX_LAYOUT_DEPTH = 2
_MAX_BLOCKS_TOTAL = 64
_RESERVED_DATA_PREFIX = "_"


def validate_dashboard_data(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("dashboard data must be a JSON object")
    for key in data:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("dashboard data keys must be non-empty strings")
        if key.startswith(_RESERVED_DATA_PREFIX) and key != "_agentlayer":
            raise ValueError(f"dashboard data key is reserved: {key!r}")


def validate_ui_layout(ui_layout: dict[str, Any]) -> None:
    if not isinstance(ui_layout, dict):
        raise ValueError("ui_layout must be a JSON object")
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("ui_layout.blocks must be a list")
    seen: set[str] = set()
    count = _validate_blocks(blocks, seen=seen, depth=0)
    if count > _MAX_BLOCKS_TOTAL:
        raise ValueError(f"ui_layout may contain at most {_MAX_BLOCKS_TOTAL} blocks")


def _validate_blocks(blocks: list[Any], *, seen: set[str], depth: int) -> int:
    if depth > _MAX_LAYOUT_DEPTH:
        raise ValueError(f"ui_layout nesting may not exceed depth {_MAX_LAYOUT_DEPTH}")
    count = 0
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("ui_layout block must be an object")
        block_id = str(block.get("id") or "").strip()
        if not block_id:
            raise ValueError("ui_layout block id is required")
        if block_id in seen:
            raise ValueError(f"duplicate ui_layout block id: {block_id}")
        seen.add(block_id)
        block_type = str(block.get("type") or "").strip()
        if not block_type:
            raise ValueError(f"ui_layout block {block_id!r} requires type")
        count += 1
        if block_type.lower() == "section":
            props = block.get("props") if isinstance(block.get("props"), dict) else {}
            nested = props.get("nested")
            if isinstance(nested, dict):
                nested_blocks = nested.get("blocks")
                if isinstance(nested_blocks, list):
                    count += _validate_blocks(nested_blocks, seen=seen, depth=depth + 1)
    return count
