"""Catalog-mode tool rebuild after the first planner round."""

from __future__ import annotations

from apps.backend.core.config import config
from apps.backend.domain.agent import _full_schema_tool_function, _registry_tool_spec_by_registered_name
from apps.backend.domain.tool_forward_policy import apply_schema_modes_to_specs


def test_catalog_after_first_round_config_default_true():
    assert config.AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND is True


def test_apply_schema_modes_all_catalog_uses_empty_properties():
    spec = _registry_tool_spec_by_registered_name("write_file")
    assert spec is not None
    fn = spec["function"]
    full = _full_schema_tool_function("write_file", fn)
    full_props = full["function"]["parameters"].get("properties") or {}
    assert "path" in full_props

    catalog_modes = {"write_file": "catalog"}
    rebuilt = apply_schema_modes_to_specs(
        [spec],
        catalog_modes,
        default_full_schema=False,
    )
    cat_props = rebuilt[0]["function"]["parameters"].get("properties") or {}
    assert cat_props == {}
    assert "path" not in cat_props


def test_catalog_rebuild_preserves_forward_specs_reference_names():
    bash = _registry_tool_spec_by_registered_name("bash")
    write = _registry_tool_spec_by_registered_name("write_file")
    assert bash is not None and write is not None
    forward_specs = [bash, write]
    modes = {
        str(s["function"]["name"]): "catalog"
        for s in forward_specs
        if isinstance(s.get("function"), dict) and s["function"].get("name")
    }
    rebuilt = apply_schema_modes_to_specs(forward_specs, modes, default_full_schema=False)
    names = [t["function"]["name"] for t in rebuilt]
    assert names == ["bash", "write_file"]
