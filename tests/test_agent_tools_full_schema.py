"""Full JSON Schema in tools[] for chat (default) and catalog mode (opt-out)."""

from apps.backend.core.config import config
from apps.backend.domain.agent import (
    _catalog_tool_function,
    _full_schema_tool_function,
    _registry_tool_spec_by_registered_name,
    _tools_for_chat_request,
)
from apps.backend.infrastructure.coding_schedule_execution import CODING_SCHEDULE_TOOL_ALLOWLIST


def test_catalog_tool_has_empty_properties():
    spec = _registry_tool_spec_by_registered_name("coding_write_file")
    assert spec is not None
    fn = spec["function"]
    out = _catalog_tool_function("coding_write_file", fn)
    props = out["function"]["parameters"].get("properties") or {}
    assert props == {}


def test_full_schema_tool_includes_write_file_path_and_content():
    spec = _registry_tool_spec_by_registered_name("coding_write_file")
    assert spec is not None
    fn = spec["function"]
    out = _full_schema_tool_function("coding_write_file", fn)
    params = out["function"]["parameters"]
    assert "path" in params.get("properties", {})
    assert "content" in params.get("properties", {})
    assert "path" in params.get("required", [])
    assert "content" in params.get("required", [])


def test_tools_for_chat_request_full_schema_larger_than_catalog():
    spec = _registry_tool_spec_by_registered_name("coding_bash")
    assert spec is not None
    catalog = _tools_for_chat_request([spec], full_schema=False)
    full = _tools_for_chat_request([spec], full_schema=True)
    cat_props = catalog[0]["function"]["parameters"].get("properties") or {}
    full_props = full[0]["function"]["parameters"].get("properties") or {}
    assert cat_props == {}
    assert "command" in full_props


def test_schedule_allowlist_includes_get_tool_help():
    assert "get_tool_help" in CODING_SCHEDULE_TOOL_ALLOWLIST


def test_tools_full_schema_default_is_true():
    assert config.AGENT_TOOLS_FULL_SCHEMA is True


def test_catalog_save_user_secret_includes_required_parameters():
    spec = _registry_tool_spec_by_registered_name("save_user_secret")
    assert spec is not None
    fn = spec["function"]
    assert fn.get("chat_full_parameters") is True
    out = _catalog_tool_function("save_user_secret", fn)
    params = out["function"]["parameters"]
    assert "service_key" in params.get("properties", {})
    assert "secret" in params.get("properties", {})
    assert "service_key" in params.get("required", [])
    assert "secret" in params.get("required", [])
