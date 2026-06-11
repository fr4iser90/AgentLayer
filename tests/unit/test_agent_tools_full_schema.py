"""Full JSON Schema in tools[] for chat (default) and catalog mode (opt-out)."""

import json

from apps.backend.core.config import config
from apps.backend.domain.agent import (
    _catalog_tool_function,
    _full_schema_tool_function,
    _registry_tool_spec_by_registered_name,
    _tools_for_chat_request,
)
from apps.backend.infrastructure.coding_schedule_execution import CODING_SCHEDULE_TOOL_ALLOWLIST


def test_catalog_tool_falls_back_to_description_field():
    fn = {
        "description": "Legacy description text",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
    }
    out = _catalog_tool_function("demo_tool", fn)
    assert "Legacy description text" in out["function"]["description"]


def test_catalog_tool_includes_required_stubs_only():
    spec = _registry_tool_spec_by_registered_name("write_file")
    assert spec is not None
    fn = spec["function"]
    out = _catalog_tool_function("write_file", fn)
    params = out["function"]["parameters"]
    props = params.get("properties") or {}
    assert "path" in props
    assert "content" in props
    assert props["path"] == {"type": "string"}
    assert "path" in params.get("required", [])
    full = _full_schema_tool_function("write_file", fn)
    full_desc = full["function"]["parameters"]["properties"]["path"]
    assert "TOOL_DESCRIPTION" in full_desc or "description" in full_desc


def test_full_schema_tool_includes_write_file_path_and_content():
    spec = _registry_tool_spec_by_registered_name("write_file")
    assert spec is not None
    fn = spec["function"]
    out = _full_schema_tool_function("write_file", fn)
    params = out["function"]["parameters"]
    assert "path" in params.get("properties", {})
    assert "content" in params.get("properties", {})
    assert "path" in params.get("required", [])
    assert "content" in params.get("required", [])


def test_tools_for_chat_request_full_schema_richer_property_docs_than_catalog():
    spec = _registry_tool_spec_by_registered_name("bash")
    assert spec is not None
    catalog = _tools_for_chat_request([spec], full_schema=False)
    full = _tools_for_chat_request([spec], full_schema=True)
    cat_params = catalog[0]["function"]["parameters"]
    full_props = full[0]["function"]["parameters"].get("properties") or {}
    assert "command" in cat_params.get("properties", {})
    assert "command" in cat_params.get("required", [])
    assert "command" in full_props
    cat_cmd = cat_params["properties"]["command"]
    full_cmd = full_props["command"]
    assert cat_cmd == {"type": "string"}
    assert len(json.dumps(full_cmd)) > len(json.dumps(cat_cmd))


def test_schedule_allowlist_includes_get_tool_help():
    assert "get_tool_help" in CODING_SCHEDULE_TOOL_ALLOWLIST


def test_tools_full_schema_default_is_false():
    assert config.AGENT_TOOLS_FULL_SCHEMA is False


def test_catalog_save_user_secret_includes_required_parameters():
    spec = _registry_tool_spec_by_registered_name("save_user_secret")
    assert spec is not None
    fn = spec["function"]
    out = _catalog_tool_function("save_user_secret", fn)
    params = out["function"]["parameters"]
    assert "service_key" in params.get("properties", {})
    assert "secret" in params.get("properties", {})
    assert "service_key" in params.get("required", [])
    assert "secret" in params.get("required", [])


def test_catalog_workspace_create_lists_all_property_stubs_name_required():
    spec = _registry_tool_spec_by_registered_name("workspace.create")
    assert spec is not None
    fn = spec["function"]
    out = _catalog_tool_function("workspace.create", fn)
    params = out["function"]["parameters"]
    assert params.get("required") == ["name"]
    props = params.get("properties") or {}
    assert set(props.keys()) == {"name", "source", "git_url", "git_branch", "bind"}
    assert props["name"] == {"type": "string"}
    assert props["source"] == {"type": "string", "enum": ["manual", "git"]}
    full = _full_schema_tool_function("workspace.create", fn)
    full_git = full["function"]["parameters"].get("properties", {}).get("git_url") or {}
    assert "TOOL_DESCRIPTION" in full_git or "description" in full_git
