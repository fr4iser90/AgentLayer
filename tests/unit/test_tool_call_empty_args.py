"""Empty / incomplete tool_calls: generic unwrap + schema validation."""

from __future__ import annotations

import json

from apps.backend.application.agent_runtime.runtime.tool_loop import (
    _normalize_tool_call_arguments,
    format_tool_call_validation_error,
    validate_tool_call_arguments,
)


def test_catalog_allows_empty_args():
    assert validate_tool_call_arguments("catalog", {}) is None


def test_messaging_send_empty_rejected_by_schema():
    err = validate_tool_call_arguments("messaging.send", {})
    assert err is not None
    assert err["error"] == "tool_call_arguments_invalid"


def test_messaging_send_missing_body_rejected():
    msgs = [{"role": "user", "content": "tell me a joke"}]
    out = _normalize_tool_call_arguments("messaging.send", {"to": "alice"}, {}, msgs, None)
    err = validate_tool_call_arguments("messaging.send", out)
    assert err is not None


def test_infer_args_from_assistant_prose_not_applied():
    assistant = {
        "content": 'I will call messaging.send({"to": "alice", "body": "hi"}) now.',
    }
    out = _normalize_tool_call_arguments(
        "messaging.send",
        {},
        assistant,
        [],
        None,
    )
    assert out == {}
    err = validate_tool_call_arguments("messaging.send", out)
    assert err is not None


def test_validation_error_json_has_hint_and_parameters():
    err = validate_tool_call_arguments("messaging.send", {})
    assert err is not None
    payload = json.loads(format_tool_call_validation_error(err))
    assert payload.get("hint")
    assert isinstance(payload.get("parameters"), dict)
    assert "properties" in payload["parameters"]


def test_tool_call_warrants_full_schema_promotion():
    from apps.backend.application.agent_runtime.runtime.tool_loop import tool_call_warrants_full_schema_promotion

    assert tool_call_warrants_full_schema_promotion(
        rejected=True, wire_args={}, normalized_args={}, result_ok=False
    )
    assert not tool_call_warrants_full_schema_promotion(
        rejected=False, wire_args={}, normalized_args={"body": "hi"}, result_ok=True
    )
    assert tool_call_warrants_full_schema_promotion(
        rejected=False, wire_args={}, normalized_args={}, result_ok=False
    )


def test_lookup_schema_exact_name_not_fuzzy_suffix():
    from apps.backend.application.agent_runtime.runtime.tool_loop import _lookup_tool_parameter_schema

    delegate = _lookup_tool_parameter_schema("delegate")
    catalog = _lookup_tool_parameter_schema("catalog")
    assert delegate is not None and catalog is not None
    assert "prompt" in set((delegate.get("properties") or {}).keys())
    err_catalog = validate_tool_call_arguments("catalog", {})
    assert err_catalog is None
