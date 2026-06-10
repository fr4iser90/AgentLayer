"""Empty / incomplete tool_calls: generic unwrap + schema validation."""

from __future__ import annotations

import json

from apps.backend.domain.agent_tools import (
    _normalize_tool_call_arguments,
    format_tool_call_validation_error,
    validate_tool_call_arguments,
)


def test_catalog_allows_empty_args():
    assert validate_tool_call_arguments("catalog", {}) is None


def test_bind_empty_rejected_by_schema_min_properties():
    err = validate_tool_call_arguments("bind", {})
    assert err is not None
    assert err["error"] == "tool_call_arguments_invalid"


def test_read_file_empty_rejected_by_schema_required():
    msgs = [{"role": "user", "content": "tell me a joke"}]
    out = _normalize_tool_call_arguments("read_file", {}, {}, msgs, None)
    err = validate_tool_call_arguments("read_file", out)
    assert err is not None
    assert "path" in err["missing_or_empty"]


def test_infer_args_from_assistant_prose():
    assistant = {
        "content": 'I will call bind({"workspace_id": "abc-123"}) now.',
    }
    out = _normalize_tool_call_arguments(
        "bind",
        {},
        assistant,
        [],
        None,
    )
    assert out.get("workspace_id") == "abc-123"
    assert validate_tool_call_arguments("bind", out) is None


def test_validation_error_json_has_hint():
    err = validate_tool_call_arguments("bash", {})
    assert err is not None
    payload = json.loads(format_tool_call_validation_error(err))
    assert payload.get("hint")
    assert "command" in payload["hint"].lower()
