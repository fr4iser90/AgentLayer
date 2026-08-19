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
    spec = _registry_tool_spec_by_registered_name("delegate")
    assert spec is not None
    fn = spec["function"]
    full = _full_schema_tool_function("delegate", fn)
    full_props = full["function"]["parameters"].get("properties") or {}
    assert "prompt" in full_props

    catalog_modes = {"delegate": "catalog"}
    rebuilt = apply_schema_modes_to_specs(
        [spec],
        catalog_modes,
        default_full_schema=False,
    )
    cat_params = rebuilt[0]["function"]["parameters"]
    cat_props = cat_params.get("properties") or {}
    assert "prompt" in cat_props
    assert "description" in cat_props


def test_catalog_includes_optional_property_stubs_for_delegate():
    spec = _registry_tool_spec_by_registered_name("delegate")
    assert spec is not None
    rebuilt = apply_schema_modes_to_specs(
        [spec],
        {"delegate": "catalog"},
        default_full_schema=False,
    )
    props = rebuilt[0]["function"]["parameters"].get("properties") or {}
    assert "prompt" in props
    assert "description" in props
    assert "run_subagent" in props


def test_catalog_rebuild_preserves_forward_specs_reference_names():
    delegate = _registry_tool_spec_by_registered_name("delegate")
    catalog = _registry_tool_spec_by_registered_name("catalog")
    assert delegate is not None and catalog is not None
    forward_specs = [delegate, catalog]
    modes = {
        str(s["function"]["name"]): "catalog"
        for s in forward_specs
        if isinstance(s.get("function"), dict) and s["function"].get("name")
    }
    rebuilt = apply_schema_modes_to_specs(forward_specs, modes, default_full_schema=False)
    names = [t["function"]["name"] for t in rebuilt]
    assert names == ["delegate", "catalog"]
