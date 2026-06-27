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


def test_infer_args_from_assistant_prose_not_applied():
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
    assert out == {}
    err = validate_tool_call_arguments("bind", out)
    assert err is not None


def test_validation_error_json_has_hint_and_parameters():
    err = validate_tool_call_arguments("bash", {})
    assert err is not None
    payload = json.loads(format_tool_call_validation_error(err))
    assert payload.get("hint")
    assert "command" in payload["hint"].lower()
    assert isinstance(payload.get("parameters"), dict)
    assert "properties" in payload["parameters"]


def test_tool_call_warrants_full_schema_promotion():
    from apps.backend.application.agent_runtime.runtime.tool_loop import tool_call_warrants_full_schema_promotion

    assert tool_call_warrants_full_schema_promotion(
        rejected=True, wire_args={}, normalized_args={}, result_ok=False
    )
    assert not tool_call_warrants_full_schema_promotion(
        rejected=False, wire_args={}, normalized_args={"command": "ls"}, result_ok=True
    )
    assert tool_call_warrants_full_schema_promotion(
        rejected=False, wire_args={}, normalized_args={}, result_ok=False
    )
    assert not tool_call_warrants_full_schema_promotion(
        rejected=False,
        wire_args={},
        normalized_args={"name": "bench"},
        result_ok=True,
    )
    assert tool_call_warrants_full_schema_promotion(
        rejected=False,
        wire_args={"name": "bench-git"},
        normalized_args={"name": "bench-git"},
        result_ok=False,
        result_error="git_url is required for source=git",
    )
    assert not tool_call_warrants_full_schema_promotion(
        rejected=False,
        wire_args={"kind": "custom", "title": "x"},
        normalized_args={"kind": "custom", "title": "x"},
        result_ok=False,
        result_error="Multiple custom dashboards exist",
    )


def test_lookup_schema_exact_name_not_fuzzy_suffix():
    from apps.backend.application.agent_runtime.runtime.tool_loop import _lookup_tool_parameter_schema

    ws = _lookup_tool_parameter_schema("workspace.create")
    bare = _lookup_tool_parameter_schema("create")
    assert ws is not None and bare is not None
    assert set(ws.get("required") or []) == {"name"}
    assert "instructions" in set((bare.get("properties") or {}).keys())
    err_ws = validate_tool_call_arguments("workspace.create", {})
    err_bare = validate_tool_call_arguments("create", {})
    assert err_ws is not None and "name" in err_ws["missing_or_empty"]
    assert err_bare is not None
    assert "instructions" in err_bare["missing_or_empty"] or "execution_target" in err_bare["missing_or_empty"]
    assert err_ws["parameters"] != err_bare["parameters"]
