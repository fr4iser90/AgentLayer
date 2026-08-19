"""Credential tools on agent allowlist (forwarded via ranking, not pins)."""

from __future__ import annotations

from apps.backend.application.agent_runtime.runtime.tool_loop import (
    _AGENT_CREDENTIAL_TOOL_NAMES,
    _credential_tools_for_agent,
    _partition_tool_specs_by_name,
)


def test_general_agent_allowlist_includes_user_secrets_status() -> None:
    pin = _credential_tools_for_agent("general")
    assert "user_secrets_status" in pin
    assert pin <= _AGENT_CREDENTIAL_TOOL_NAMES


def test_partition_tool_specs_by_name() -> None:
    specs = [
        {"type": "function", "function": {"name": "catalog"}},
        {"type": "function", "function": {"name": "user_secrets_status"}},
        {"type": "function", "function": {"name": "delegate"}},
    ]
    pinned, rest = _partition_tool_specs_by_name(specs, frozenset({"user_secrets_status"}))
    assert [t["function"]["name"] for t in pinned] == ["user_secrets_status"]
    assert len(rest) == 2
