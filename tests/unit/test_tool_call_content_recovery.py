"""Tests for prose / markup → wire tool_calls recovery."""

from __future__ import annotations

import json

from apps.backend.domain.agent_turn_hooks import turn_hooks_for_agent
from apps.backend.domain.tool_call_content_recovery import (
    recover_tool_calls_from_assistant_content,
)


def _allowed(*names: str) -> set[str]:
    return set(names)


def test_recovers_catalog_from_json_content():
    msg = {
        "role": "assistant",
        "content": '{"tool": "catalog", "parameters": {}}',
    }
    tc = recover_tool_calls_from_assistant_content(msg, allowed_tool_names=_allowed("catalog"))
    assert tc is not None
    assert tc[0]["function"]["name"] == "catalog"
    assert json.loads(tc[0]["function"]["arguments"]) == {}


def test_recovers_workspace_create_parenthesized():
    args = {"name": "bench-git", "git_url": "https://github.com/octocat/Hello-World.git"}
    msg = {
        "role": "assistant",
        "content": f'workspace.create({json.dumps(args)})',
    }
    tc = recover_tool_calls_from_assistant_content(
        msg,
        allowed_tool_names=_allowed("workspace.create"),
    )
    assert tc is not None
    assert tc[0]["function"]["name"] == "workspace.create"
    assert json.loads(tc[0]["function"]["arguments"]) == args


def test_fuzzy_workspaces_create_name():
    msg = {
        "role": "assistant",
        "content": 'workspaces.create({"name": "bench-x"})',
    }
    tc = recover_tool_calls_from_assistant_content(
        msg,
        allowed_tool_names=_allowed("workspace.create"),
    )
    assert tc is not None
    assert tc[0]["function"]["name"] == "workspace.create"


def test_recovers_delegate_from_reasoning_channel():
    payload = {"agent_id": "math", "prompt": "compute 17*23"}
    msg = {
        "role": "assistant",
        "content": "I'll delegate this.",
        "reasoning_content": json.dumps({"name": "delegate", "arguments": payload}),
    }
    tc = recover_tool_calls_from_assistant_content(
        msg,
        allowed_tool_names=_allowed("delegate"),
    )
    assert tc is not None
    assert tc[0]["function"]["name"] == "delegate"
    assert json.loads(tc[0]["function"]["arguments"]) == payload


def test_recovers_fake_function_markup():
    msg = {
        "role": "assistant",
        "content": '<function=catalog></function>',
    }
    tc = recover_tool_calls_from_assistant_content(msg, allowed_tool_names=_allowed("catalog"))
    assert tc is not None
    assert tc[0]["function"]["name"] == "catalog"


def test_recovers_invoke_parameter_markup():
    msg = {
        "role": "assistant",
        "content": (
            '<invoke name="workspace.create">'
            '<parameter name="name">bench-ws</parameter>'
            '<parameter name="git_url">https://github.com/octocat/Hello-World.git</parameter>'
            "</invoke>"
        ),
    }
    tc = recover_tool_calls_from_assistant_content(
        msg,
        allowed_tool_names=_allowed("workspace.create"),
    )
    assert tc is not None
    args = json.loads(tc[0]["function"]["arguments"])
    assert args["name"] == "bench-ws"
    assert "git_url" in args


def test_skips_tool_not_in_allowlist():
    msg = {"role": "assistant", "content": '{"tool": "catalog", "parameters": {}}'}
    tc = recover_tool_calls_from_assistant_content(msg, allowed_tool_names=_allowed("delegate"))
    assert tc is None


def test_general_turn_hooks_delegate_to_recovery(monkeypatch):
    monkeypatch.setattr(
        "apps.backend.domain.agent_turn_hooks._agent_behavior_flags",
        lambda aid: {"tool_discipline_preset": None},
    )
    hooks = turn_hooks_for_agent("general")
    msg = {"role": "assistant", "content": '{"tool": "catalog", "parameters": {}}'}
    tc = hooks.recover_tool_calls_from_message(
        msg,
        allowed_tool_names={"catalog"},
        tools_for_round=[{"type": "function", "function": {"name": "catalog"}}],
    )
    assert tc is not None
    assert tc[0]["function"]["name"] == "catalog"
