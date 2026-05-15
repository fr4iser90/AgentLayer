"""MCP wiring: function-name encoding and server JSON parsing (no live stdio servers)."""

from __future__ import annotations

import json

import pytest

from apps.backend.infrastructure.mcp_runtime import (
    McpStdioServer,
    _parse_servers_payload,
    mcp_openai_function_name,
    parse_mcp_openai_function_name,
)


def test_mcp_function_name_roundtrip() -> None:
    sid = "fetch"
    for tool in ("read", "foo/bar", "über"):
        fn = mcp_openai_function_name(sid, tool)
        assert fn.startswith("mcp__fetch__")
        parsed = parse_mcp_openai_function_name(fn)
        assert parsed == (sid, tool)


def test_parse_mcp_openai_function_name_invalid() -> None:
    assert parse_mcp_openai_function_name("") is None
    assert parse_mcp_openai_function_name("coding_bash") is None
    assert parse_mcp_openai_function_name("mcp__bad_id__abc") is None


def test_parse_servers_payload() -> None:
    rows = [
        {
            "id": "s1",
            "command": "uvx",
            "args": ["tool"],
            "env": {"FOO": "bar"},
            "cwd": "/tmp",
        }
    ]
    servers = _parse_servers_payload(rows)
    assert servers == [
        McpStdioServer(server_id="s1", command="uvx", args=["tool"], env={"FOO": "bar"}, cwd="/tmp")
    ]


def test_parse_servers_rejects_bad_id() -> None:
    with pytest.raises(ValueError, match="server id"):
        _parse_servers_payload(
            [{"id": "bad_id", "command": "x", "args": []}],
        )


def test_mcp_runtime_status_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.backend.core.config as cfg_mod
    import asyncio

    monkeypatch.setattr(cfg_mod, "AGENT_MCP_ENABLED", False, raising=False)

    from apps.backend.infrastructure.mcp_runtime import mcp_runtime_status

    st = asyncio.run(mcp_runtime_status())
    assert st["enabled"] is False
    assert st["servers"] == []


    import apps.backend.core.config as cfg_mod

    payload = [{"id": "x", "command": "true", "args": []}]
    monkeypatch.setattr(cfg_mod, "AGENT_MCP_SERVERS_FILE", "", raising=False)
    monkeypatch.setattr(cfg_mod, "AGENT_MCP_SERVERS_JSON", json.dumps(payload), raising=False)
    from apps.backend.infrastructure import mcp_runtime

    servers = mcp_runtime.load_mcp_stdio_servers()
    assert len(servers) == 1
    assert servers[0].server_id == "x"
    assert servers[0].command == "true"
