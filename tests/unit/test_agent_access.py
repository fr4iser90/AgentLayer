"""Agent invoke allowlist (end users → general only)."""

from __future__ import annotations

from apps.backend.domain.agent_runtime.access import (
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
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    ag = get_agent_registry().get_agent("general")
    assert ag is not None
    names = ag.get("tool_names") or []
    assert names == sorted(
        ["bind", "catalog", "delegate", "user_secrets_status", "workspace.create", "workspace.list"]
    )
    assert "delegate" in names
    assert "catalog" in names
    assert "task" not in names
    assert "read_file" not in names
    assert "repository.read_file" not in names
    assert "bash" not in names
    assert "edit" not in names
    assert "git_push" not in names
