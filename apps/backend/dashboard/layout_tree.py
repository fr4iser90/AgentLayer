"""Nested dashboard layout helpers (section blocks, block-id flattening)."""

from __future__ import annotations

from typing import Any


MAX_LAYOUT_DEPTH = 2
MAX_BLOCKS_TOTAL = 64


def empty_nested_layout() -> dict[str, Any]:
    return {"version": 2, "blocks": []}


def normalize_nested_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_nested_layout()
    blocks = raw.get("blocks")
    if not isinstance(blocks, list):
        return empty_nested_layout()
    return {"version": 2, "blocks": blocks}


def flatten_block_ids(ui_layout: dict[str, Any] | None) -> list[str]:
    if not isinstance(ui_layout, dict):
        return []
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, list):
        return []
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if bid:
            out.append(bid)
        if str(b.get("type") or "").strip().lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = normalize_nested_layout(props.get("nested"))
            for nb in nested.get("blocks") or []:
                if not isinstance(nb, dict):
                    continue
                nid = str(nb.get("id") or "").strip()
                if nid:
                    out.append(nid)
    return out


def count_layout_blocks(ui_layout: dict[str, Any] | None) -> int:
    return len(flatten_block_ids(ui_layout))


def section_nested_props(section_block: dict[str, Any]) -> dict[str, Any]:
    props = section_block.setdefault("props", {})
    if not isinstance(props, dict):
        props = {}
        section_block["props"] = props
    nested = normalize_nested_layout(props.get("nested"))
    props["nested"] = nested
    return props


def nested_blocks_list(section_block: dict[str, Any]) -> list[Any]:
    props = section_nested_props(section_block)
    nested = props.get("nested")
    if not isinstance(nested, dict):
        nested = empty_nested_layout()
        props["nested"] = nested
    blocks = nested.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
        nested["blocks"] = blocks
    return blocks


def resolve_blocks_target(
    ui_layout: dict[str, Any], parent_block_id: str | None
) -> tuple[list[Any] | None, str | None]:
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
        ui_layout["blocks"] = blocks
    if not parent_block_id:
        return blocks, None
    pid = parent_block_id.strip()
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if str(b.get("id") or "").strip() != pid:
            continue
        if str(b.get("type") or "").strip().lower() != "section":
            return None, f"parent_block_id {pid!r} is not a section"
        return nested_blocks_list(b), None
    return None, f"unknown parent_block_id {pid!r}"


def find_block_by_id(ui_layout: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    bid = block_id.strip()
    blocks = ui_layout.get("blocks")
    if not isinstance(blocks, list):
        return None
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if str(b.get("id") or "").strip() == bid:
            return b
        if str(b.get("type") or "").strip().lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = normalize_nested_layout(props.get("nested"))
            for nb in nested.get("blocks") or []:
                if isinstance(nb, dict) and str(nb.get("id") or "").strip() == bid:
                    return nb
    return None


def data_paths_from_blocks(blocks: list[Any]) -> list[str]:
    paths: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        props = b.get("props")
        if isinstance(props, dict):
            dp = str(props.get("dataPath") or "").strip()
            if dp:
                paths.append(dp)
        if str(b.get("type") or "").strip().lower() == "section":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            nested = normalize_nested_layout(props.get("nested"))
            paths.extend(data_paths_from_blocks(nested.get("blocks") or []))
    return paths


def filter_layout_blocks(blocks: list[Any], allowed: frozenset[str]) -> list[Any]:
    out: list[Any] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if bid not in allowed:
            continue
        if str(b.get("type") or "").strip().lower() == "section":
            nb = dict(b)
            props = dict(nb.get("props") or {}) if isinstance(nb.get("props"), dict) else {}
            nested = normalize_nested_layout(props.get("nested"))
            nested_blocks = nested.get("blocks") or []
            filtered_nested = filter_layout_blocks(nested_blocks, allowed)
            props["nested"] = {**nested, "blocks": filtered_nested}
            nb["props"] = props
            out.append(nb)
        else:
            out.append(b)
    return out
