"""Unit tests for dashboard layout tree helpers."""

from __future__ import annotations

from apps.backend.infrastructure.dashboards.dashboard_layout_tree import (
    count_layout_blocks,
    filter_layout_blocks,
    find_block_in_layout,
    flatten_block_ids,
)


def test_flatten_block_ids_includes_nested() -> None:
    ul = {
        "version": 2,
        "blocks": [
            {"id": "root_a", "type": "hero", "grid": {}, "props": {}},
            {
                "id": "sec_1",
                "type": "section",
                "grid": {},
                "props": {
                    "nested": {
                        "version": 2,
                        "blocks": [{"id": "inner_b", "type": "stat", "grid": {}, "props": {}}],
                    }
                },
            },
        ],
    }
    ids = flatten_block_ids(ul)
    assert ids == ["root_a", "sec_1", "inner_b"]
    assert count_layout_blocks(ul) == 3


def test_filter_layout_blocks_keeps_section_with_allowed_children() -> None:
    blocks = [
        {
            "id": "sec_1",
            "type": "section",
            "grid": {},
            "props": {
                "nested": {
                    "version": 2,
                    "blocks": [
                        {"id": "a", "type": "markdown", "grid": {}, "props": {}},
                        {"id": "b", "type": "stat", "grid": {}, "props": {}},
                    ],
                }
            },
        }
    ]
    filtered = filter_layout_blocks(blocks, frozenset({"sec_1", "a"}))
    assert len(filtered) == 1
    nested = filtered[0]["props"]["nested"]["blocks"]
    assert len(nested) == 1
    assert nested[0]["id"] == "a"


def test_find_block_in_layout_root_and_nested() -> None:
    ul = {
        "version": 2,
        "blocks": [
            {"id": "root_a", "type": "hero", "grid": {}, "props": {"title": "Hero"}},
            {
                "id": "sec_1",
                "type": "section",
                "grid": {},
                "props": {
                    "nested": {
                        "version": 2,
                        "blocks": [{"id": "inner_b", "type": "stat", "grid": {}, "props": {}}],
                    }
                },
            },
        ],
    }
    root = find_block_in_layout(ul, "root_a")
    assert root is not None
    assert root["type"] == "hero"
    inner = find_block_in_layout(ul, "inner_b")
    assert inner is not None
    assert inner["type"] == "stat"
    assert find_block_in_layout(ul, "missing") is None
