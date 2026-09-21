"""Unit tests for the UX-audit seed's pure layout builder.

``build_layout_and_data`` is ~300 lines of pure construction (no I/O) that emits
the dashboard layout + demo payload the live seed POSTs to the API. Before this it
was covered only by a live run, so a typo in a ``dataPath`` or a missing ``y += h``
surfaced as a broken dashboard in a browser, not as a failing test.

These assert the invariants the frontend actually relies on:

* the layout is JSON-serialisable (it is POSTed as-is)
* the 12-col grid stacks without overlap (``row()`` must advance ``y`` by ``h``)
* every ``dataPath`` a block references exists in ``data`` (a typo = empty block)
* every ``data`` key is consumed by some block (an orphan = dead demo payload)
* the caller's ids are threaded into the blocks that need them
* the builder is deterministic (the seed deletes-then-creates; drift would be silent)
* the seed covers every ``BlockType`` the frontend declares, parsed from types.ts
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEED_PATH = REPO / "scripts" / "seed_dashboard_ux_audit.py"
FRONTEND_TYPES = REPO / "apps" / "frontend" / "src" / "features" / "dashboard" / "types.ts"

ARGS = {
    "source_dash_id": "dash-source-1",
    "source_block_id": "block-source-9",
    "friend_user_id": "user-friend-7",
}


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_dashboard_ux_audit", SEED_PATH)
    assert spec and spec.loader, f"cannot load {SEED_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built():
    module = _load_seed_module()
    return module.build_layout_and_data(**ARGS)


@pytest.fixture(scope="module")
def layout(built):
    return built[0]


@pytest.fixture(scope="module")
def data(built):
    return built[1]


def _by_id(blocks: list[dict], block_id: str) -> dict:
    for block in blocks:
        if block.get("id") == block_id:
            return block
    raise AssertionError(f"block {block_id!r} not found")


def _collect_data_paths(blocks: list[dict]) -> list[str]:
    """dataPath of each block, descending into a section's nested layout."""
    found: list[str] = []
    for block in blocks:
        props = block.get("props") or {}
        if "dataPath" in props:
            found.append(props["dataPath"])
        nested = props.get("nested")
        if isinstance(nested, dict):
            found.extend(_collect_data_paths(nested.get("blocks") or []))
    return found


def test_layout_is_json_serialisable(layout, data):
    # The seed POSTs these verbatim; a non-serialisable value fails only at runtime.
    round_tripped = json.loads(json.dumps({"layout": layout, "data": data}))
    assert round_tripped == {"layout": layout, "data": data}


def test_layout_version_is_two(layout):
    assert layout["version"] == 2


def test_every_block_has_the_required_shape(layout):
    for block in layout["blocks"]:
        assert set(block) >= {"id", "type", "grid", "props"}, block
        assert set(block["grid"]) == {"x", "y", "w", "h"}, block["id"]
        assert all(isinstance(block["grid"][k], int) for k in ("x", "y", "w", "h")), block["id"]


def test_block_ids_are_unique(layout):
    ids = [b["id"] for b in layout["blocks"]]
    assert len(ids) == len(set(ids)), f"duplicate block ids: {ids}"


def test_grid_stacks_without_overlap(layout):
    """row() advances a shared cursor by h; a missed increment would overlap blocks."""
    cursor = 0
    for block in layout["blocks"]:
        grid = block["grid"]
        assert grid["x"] == 0, f"{block['id']} must start at column 0"
        assert grid["w"] == 12, f"{block['id']} must span the full 12-col width"
        assert grid["y"] == cursor, f"{block['id']} starts at y={grid['y']}, expected {cursor}"
        cursor += grid["h"]
    assert cursor == sum(b["grid"]["h"] for b in layout["blocks"])


def test_every_data_path_resolves(layout, data):
    paths = _collect_data_paths(layout["blocks"])
    assert paths, "expected at least one dataPath"
    missing = sorted(p for p in paths if p not in data)
    assert not missing, f"blocks reference dataPaths absent from data: {missing}"


def test_no_data_key_is_unconsumed(layout, data):
    consumed = set(_collect_data_paths(layout["blocks"]))
    orphans = sorted(set(data) - consumed)
    assert not orphans, f"data keys no block reads: {orphans}"


def test_nested_section_block_is_a_valid_layout(layout, data):
    section = _by_id(layout["blocks"], "demo-section")
    nested = section["props"]["nested"]
    assert nested["version"] == 2
    assert len(nested["blocks"]) == 1
    inner = nested["blocks"][0]
    assert inner["type"] == "markdown"
    assert inner["props"]["dataPath"] in data
    # "section" is the one type nesting disallows; a nested section would recurse forever.
    assert "section" != inner["type"]


def test_caller_ids_are_threaded_into_their_blocks(layout):
    share = _by_id(layout["blocks"], "demo-share")
    assert share["props"]["friendUserId"] == ARGS["friend_user_id"]

    ref = _by_id(layout["blocks"], "demo-ref")
    assert ref["props"]["sourceDashboardId"] == ARGS["source_dash_id"]
    assert ref["props"]["sourceBlockId"] == ARGS["source_block_id"]


def test_builder_is_deterministic():
    module = _load_seed_module()
    first = module.build_layout_and_data(**ARGS)
    second = module.build_layout_and_data(**ARGS)
    assert first == second, "same args must produce identical layout and data"


def test_builder_is_pure_no_shared_cursor_between_calls():
    """row() mutates a closure cursor; a leaked module-level cursor would shift the
    second call's grid even though the output dicts look alike."""
    module = _load_seed_module()
    a, _ = module.build_layout_and_data(**ARGS)
    b, _ = module.build_layout_and_data(**ARGS)
    assert [x["grid"] for x in a["blocks"]] == [x["grid"] for x in b["blocks"]]


def test_seed_covers_every_frontend_block_type(layout):
    """Parsed from the frontend's BlockType union, not a copy of it.

    The audit board exists to exercise every block visually. If the frontend gains a
    BlockType and the seed is not extended, the new block ships never-screenshotted —
    exactly the class of defect the vision pass cannot catch because it is absent.
    """
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    union = re.search(r"export type BlockType =\s*((?:\s*\|[\s\"]*[a-z_]+\")+)", source)
    assert union, f"could not parse BlockType union from {FRONTEND_TYPES}"
    declared = set(re.findall(r'"([a-z_]+)"', union.group(1)))
    assert declared, "parsed an empty BlockType union"

    seeded = {b["type"] for b in layout["blocks"]}
    missing = sorted(declared - seeded)
    assert not missing, (
        f"frontend declares BlockTypes the audit seed never renders: {missing}. "
        "Extend build_layout_and_data so the new block gets screenshotted."
    )
    unknown = sorted(seeded - declared)
    assert not unknown, f"seed renders block types the frontend does not declare: {unknown}"


def test_seed_module_exposes_the_live_helpers():
    """Guard the seam: main() depends on these, a rename breaks the seed stage."""
    module = _load_seed_module()
    for name in (
        "_ensure_schema",
        "_login_as",
        "_delete_by_title",
        "_ensure_friend_for_share",
        "_seed_scheduler_jobs",
        "build_layout_and_data",
        "main",
    ):
        assert callable(getattr(module, name)), f"{name} missing from seed module"
