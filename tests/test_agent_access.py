"""Agent invoke allowlist (end users → general only)."""

from __future__ import annotations

from apps.backend.domain.agent_access import (
    default_agent_for_workspace,
    user_may_invoke_agent,
)


def test_enduser_may_only_invoke_general() -> None:
    ok, _ = user_may_invoke_agent("user", "general")
    assert ok is True
    ok, err = user_may_invoke_agent("user", "coding")
    assert ok is False
    assert "not available" in err.lower()


def test_admin_may_invoke_coding() -> None:
    ok, _ = user_may_invoke_agent("admin", "coding")
    assert ok is True


def test_admin_only_agent_blocked_for_user() -> None:
    ok, err = user_may_invoke_agent("user", "operator")
    assert ok is False
    assert "admin" in err.lower()


def test_default_agent_for_workspace_by_role() -> None:
    assert default_agent_for_workspace("user") == "general"
    assert default_agent_for_workspace("admin") == "coding"


def test_general_agent_has_no_bash_or_push_tools() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    ag = get_agent_registry().get_agent("general")
    assert ag is not None
    names = ag.get("tool_names") or []
    assert "coding_task" in names
    assert "agent_delegate" in names
    assert "coding_read_file" in names
    assert "coding_bash" not in names
    assert "coding_edit" not in names
    assert "coding_git_push" not in names
