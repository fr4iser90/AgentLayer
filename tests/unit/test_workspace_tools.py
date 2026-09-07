"""Tests for workspace management tools (normalize URL, registry)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.application.agent_runtime.use_cases.workspace_bind import workspace_tool_bound_workspace_id
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


def test_git_url_equivalence_key() -> None:
    from apps.backend.domain.workspace.workspace_common import git_url_equivalence_key

    a = "https://github.com/fr4iser90/AgentLayer.git"
    b = "https://github.com/fr4iser90/AgentLayer"
    c = "HTTPS://GitHub.com/fr4iser90/AgentLayer/"
    assert git_url_equivalence_key(a) == git_url_equivalence_key(b) == git_url_equivalence_key(c)


def test_find_owned_git_workspace_scoped_to_owner() -> None:
    from apps.backend.domain.workspace.workspace_common import find_owned_git_workspace

    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    user_a = MagicMock()
    user_a.id = uid_a

    row_a = (
        uuid.uuid4(),
        uid_a,
        "AgentLayer-deadbeef",
        "/data/ws",
        "git",
        "https://github.com/fr4iser90/AgentLayer",
        "main",
        "owner",
        None,
        None,
        None,
        False,
        None,
        True,
        True,
        None,
        None,
        None,
        True,
        None,
        None,
        None,
        None,
        True,
        None,
    )

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = [row_a]
    conn.cursor.return_value.__enter__.return_value = cur
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn

    git_url = "https://github.com/fr4iser90/AgentLayer.git"
    with patch("apps.backend.domain.workspace.workspace_common.db.pool", return_value=pool):
        found = find_owned_git_workspace(user_a, git_url=git_url)

    assert found is not None
    assert found["name"] == "AgentLayer-deadbeef"
    assert cur.execute.call_args[0][1] == (uid_a,)

    user_b = MagicMock()
    user_b.id = uid_b
    cur.fetchall.return_value = []
    with patch("apps.backend.domain.workspace.workspace_common.db.pool", return_value=pool):
        assert find_owned_git_workspace(user_b, git_url=git_url) is None
    assert cur.execute.call_args[0][1] == (uid_b,)


def testworkspace_tool_bound_workspace_id() -> None:
    payload = (
        '{"ok": true, "bound": true, "workspace": {"id": "abc-123", "name": "PIDEA"}}'
    )
    assert workspace_tool_bound_workspace_id("workspace.create", payload) == "abc-123"
    assert workspace_tool_bound_workspace_id("bind", payload) == "abc-123"
    assert workspace_tool_bound_workspace_id("workspace.create", '{"ok": true, "bound": false}') is None


def test_coding_agent_includes_workspace_tools() -> None:
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    names = a["tool_names"]
    assert "workspace.list" in names
    assert "workspace.create" in names
    assert "bind" in names
