"""Agent invoke allowlist (end users → general only)."""

from __future__ import annotations

from apps.backend.domain.agent_runtime.access import (
    default_agent_for_workspace,
    user_may_invoke_agent,
)


def test_enduser_may_only_invoke_general() -> None:
    ok, _ = user_may_invoke_agent("user", "general")
    assert ok is True
    ok, err = user_may_invoke_agent("user", "research")
    assert ok is False
    assert "not available" in err.lower()


def test_enduser_may_invoke_knowledge_companion() -> None:
    ok, err = user_may_invoke_agent("user", "knowledge_companion")
    assert ok is True, err


def test_enduser_knowledge_companion_with_governance_deps() -> None:
    from unittest.mock import MagicMock

    from apps.backend.domain.agent_runtime import access as access_mod

    mock_deps = MagicMock()
    mock_deps.list_agent_policies.return_value = []
    prev = access_mod._deps
    access_mod.register_agent_access_dependencies(mock_deps)
    try:
        ok, err = access_mod.user_may_invoke_agent(
            "user",
            "knowledge_companion",
            tenant_id=1,
        )
        assert ok is True, err
        ok, err = access_mod.user_may_invoke_agent("user", "research", tenant_id=1)
        assert ok is False
    finally:
        access_mod._deps = prev


def test_admin_may_invoke_research() -> None:
    ok, _ = user_may_invoke_agent("admin", "research")
    assert ok is True


def test_admin_only_agent_blocked_for_user() -> None:
    ok, err = user_may_invoke_agent("user", "operator")
    assert ok is False
    assert "admin" in err.lower()


def test_default_agent_for_workspace_is_general() -> None:
    assert default_agent_for_workspace("user") == "general"
    assert default_agent_for_workspace("admin") == "general"


def test_general_agent_has_no_bash_or_push_tools() -> None:
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    ag = get_agent_registry().get_agent("general")
    assert ag is not None
    names = ag.get("tool_names") or []
    assert names == sorted(["catalog", "delegate", "user_secrets_status"])
    assert "delegate" in names
    assert "catalog" in names
    assert "task" not in names
    assert "read_file" not in names
    assert "repository.read_file" not in names
    assert "bash" not in names
    assert "edit" not in names
    assert "git_push" not in names
