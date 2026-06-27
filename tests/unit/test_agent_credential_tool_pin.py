"""Credential tools on agent allowlist (forwarded via ranking, not pins)."""

from __future__ import annotations

from apps.backend.application.agent_runtime.runtime.tool_loop import (
    _AGENT_CREDENTIAL_TOOL_NAMES,
    _credential_tools_for_agent,
    _partition_tool_specs_by_name,
)


def test_coding_agent_allowlist_includes_save_user_secret() -> None:
    pin = _credential_tools_for_agent("coding")
    assert "save_user_secret" in pin
    assert pin <= _AGENT_CREDENTIAL_TOOL_NAMES


def test_partition_tool_specs_by_name() -> None:
    specs = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "save_user_secret"}},
        {"type": "function", "function": {"name": "list"}},
    ]
    pinned, rest = _partition_tool_specs_by_name(specs, frozenset({"save_user_secret"}))
    assert [t["function"]["name"] for t in pinned] == ["save_user_secret"]
    assert len(rest) == 2
