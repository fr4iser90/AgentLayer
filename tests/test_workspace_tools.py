"""Tests for workspace management tools (normalize URL, registry)."""

from __future__ import annotations

from apps.backend.domain.agent import _workspace_tool_bound_workspace_id
from apps.backend.domain.workspace.workspace_common import normalize_git_url


def test_normalize_git_url_https() -> None:
    assert (
        normalize_git_url("https://github.com/fr4iser90/PIDEA")
        == "https://github.com/fr4iser90/PIDEA"
    )


def test_normalize_git_url_owner_repo() -> None:
    assert (
        normalize_git_url("fr4iser90/PIDEA")
        == "https://github.com/fr4iser90/PIDEA.git"
    )


def test_workspace_tool_bound_workspace_id() -> None:
    payload = (
        '{"ok": true, "bound": true, "workspace": {"id": "abc-123", "name": "PIDEA"}}'
    )
    assert _workspace_tool_bound_workspace_id("workspace.create", payload) == "abc-123"
    assert _workspace_tool_bound_workspace_id("bind", payload) == "abc-123"
    assert _workspace_tool_bound_workspace_id("workspace.create", '{"ok": true, "bound": false}') is None


def test_coding_agent_includes_workspace_tools() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    names = a["tool_names"]
    assert "workspace.list" in names
    assert "workspace.create" in names
    assert "bind" in names
