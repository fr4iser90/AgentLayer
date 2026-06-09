"""Nested dashboard layout tree helpers."""

from __future__ import annotations

import plugins.tools.personal.dashboard.dashboard as mod


def test_add_section_block_sets_version_2() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {}
    new_ul, _, err = mod._apply_layout_ops(
        ul, data, [{"op": "add_block", "type": "section"}], allowed_block_ids=None
    )
    assert err is None
    assert new_ul["version"] == 2
    assert len(new_ul["blocks"]) == 1
    assert new_ul["blocks"][0]["type"] == "section"
    nested = new_ul["blocks"][0]["props"]["nested"]
    assert nested["version"] == 2
    assert nested["blocks"] == []


def test_add_nested_block_in_section() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {}
    new_ul, new_data, err = mod._apply_layout_ops(
        ul, data, [{"op": "add_block", "type": "section"}], allowed_block_ids=None
    )
    assert err is None
    section_id = new_ul["blocks"][0]["id"]
    new_ul, new_data, err = mod._apply_layout_ops(
        new_ul,
        new_data,
        [
            {
                "op": "add_block",
                "type": "markdown",
                "parent_block_id": section_id,
            }
        ],
        allowed_block_ids=None,
    )
    assert err is None
    nested_blocks = new_ul["blocks"][0]["props"]["nested"]["blocks"]
    assert len(nested_blocks) == 1
    assert nested_blocks[0]["type"] == "markdown"
    dp = nested_blocks[0]["props"]["dataPath"]
    assert dp in new_data


def test_cannot_nest_section_in_section() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {}
    new_ul, new_data, err = mod._apply_layout_ops(
        ul, data, [{"op": "add_block", "type": "section"}], allowed_block_ids=None
    )
    section_id = new_ul["blocks"][0]["id"]
    _, _, err = mod._apply_layout_ops(
        new_ul,
        new_data,
        [{"op": "add_block", "type": "section", "parent_block_id": section_id}],
        allowed_block_ids=None,
    )
    assert err is not None
    assert "cannot nest section" in err


def test_add_card_grid_block() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {"projects": [{"id": "p1", "title": "A"}]}
    new_ul, new_data, err = mod._apply_layout_ops(
        ul,
        data,
        [{"op": "add_block", "type": "card_grid", "data_path": "projects"}],
        allowed_block_ids=None,
    )
    assert err is None
    assert new_ul["blocks"][0]["type"] == "card_grid"
    assert new_ul["blocks"][0]["props"]["dataPath"] == "projects"
    assert new_data["projects"] == [{"id": "p1", "title": "A"}]


def test_set_grid_on_nested_block() -> None:
    ul = {"version": 1, "blocks": []}
    data: dict = {}
    new_ul, new_data, err = mod._apply_layout_ops(
        ul, data, [{"op": "add_block", "type": "section"}], allowed_block_ids=None
    )
    section_id = new_ul["blocks"][0]["id"]
    new_ul, new_data, err = mod._apply_layout_ops(
        new_ul,
        new_data,
        [{"op": "add_block", "type": "stat", "parent_block_id": section_id}],
        allowed_block_ids=None,
    )
    nested_id = new_ul["blocks"][0]["props"]["nested"]["blocks"][0]["id"]
    new_ul, _, err = mod._apply_layout_ops(
        new_ul,
        new_data,
        [{"op": "set_grid", "block_id": nested_id, "grid": {"x": 0, "y": 0, "w": 4, "h": 4}}],
        allowed_block_ids=None,
    )
    assert err is None
    grid = new_ul["blocks"][0]["props"]["nested"]["blocks"][0]["grid"]
    assert grid["w"] == 4
