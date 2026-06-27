"""Catalog-mode tool rebuild after the first planner round."""

from __future__ import annotations

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
from apps.backend.domain.agent_runtime.tool_catalog import _full_schema_tool_function
from apps.backend.domain.agent_runtime.tool_schema import _registry_tool_spec_by_registered_name
from apps.backend.domain.tools.forward_policy import apply_schema_modes_to_specs


def test_catalog_after_first_round_config_default_true():
    assert config.AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND is True


def test_apply_schema_modes_catalog_uses_required_stubs_not_full_schema():
    spec = _registry_tool_spec_by_registered_name("write_file")
    assert spec is not None
    fn = spec["function"]
    full = _full_schema_tool_function("write_file", fn)
    full_props = full["function"]["parameters"].get("properties") or {}
    assert "path" in full_props
    assert "TOOL_DESCRIPTION" in full_props["path"] or "description" in full_props["path"]

    catalog_modes = {"write_file": "catalog"}
    rebuilt = apply_schema_modes_to_specs(
        [spec],
        catalog_modes,
        default_full_schema=False,
    )
    cat_params = rebuilt[0]["function"]["parameters"]
    cat_props = cat_params.get("properties") or {}
    assert set(cat_props.keys()) == {"path", "content"}
    assert cat_props["path"] == {"type": "string"}
    assert "TOOL_DESCRIPTION" not in cat_props["path"]
    assert "path" in cat_params.get("required", [])


def test_catalog_includes_optional_property_stubs_for_workspace_create():
    spec = _registry_tool_spec_by_registered_name("workspace.create")
    assert spec is not None
    rebuilt = apply_schema_modes_to_specs(
        [spec],
        {"workspace.create": "catalog"},
        default_full_schema=False,
    )
    props = rebuilt[0]["function"]["parameters"].get("properties") or {}
    assert "name" in props
    assert "git_url" in props
    assert "source" in props
    assert props["source"].get("enum") == ["manual", "git"]


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
