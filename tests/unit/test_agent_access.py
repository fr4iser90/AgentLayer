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


def test_default_agent_for_workspace_by_role() -> None:
    assert default_agent_for_workspace("user") == "general"
    assert default_agent_for_workspace("admin") == "coding"


def test_general_agent_has_no_bash_or_push_tools() -> None:
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    ag = get_agent_registry().get_agent("general")
    assert ag is not None
    names = ag.get("tool_names") or []
    assert names == sorted(
        [
            "bind",
            "catalog",
            "delegate",
            "env_bindings",
            "exit_plan_mode",
            "goal_create",
            "goal_get",
            "goal_update",
            "plan_mode_set",
            "register_secrets",
            "request_user_secret",
            "save_user_secret",
            "secrets_help",
            "todo_read",
            "todo_write",
            "user_secrets_status",
            "workspace.create",
            "workspace.list",
        ]
    )
    assert "delegate" in names
    assert "catalog" in names
    assert "task" not in names
    assert "read_file" not in names
    assert "repository.read_file" not in names
    assert "bash" not in names
    assert "edit" not in names
    assert "git_push" not in names


# --- P1: site_role drives elevation (not the legacy ``users.role='admin'``) ---


def test_user_site_admin_follows_site_role() -> None:
    from unittest.mock import patch

    from apps.backend.infrastructure.db import identity_tenants

    with patch.object(identity_tenants, "user_site_role", return_value="site_user"):
        assert identity_tenants.user_site_admin("some-uuid") is False
    with patch.object(identity_tenants, "user_site_role", return_value="site_admin"):
        assert identity_tenants.user_site_admin("some-uuid") is True
    assert identity_tenants.user_site_admin(None) is None


def test_is_elevated_admin_prefers_site_role_over_legacy_role() -> None:
    import uuid

    from unittest.mock import patch

    from apps.backend.application.agent_runtime.use_cases import auto_workspace as aw_mod

    # role='admin' but site_role='site_user' → NOT elevated, even if the JWT
    # bearer claims admin. This is the P1 Done-When core.
    with patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=False):
        class _U:
            role = "admin"

        assert aw_mod.is_elevated_admin(_U(), "admin", uuid.uuid4()) is False

    # site_role='site_admin' → elevated regardless of the legacy role field.
    with patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=True):
        assert aw_mod.is_elevated_admin(None, None, uuid.uuid4()) is True

    # Legacy fallback: site_role unknown (None) → raw role signal counts.
    with patch("apps.backend.infrastructure.db.db.user_site_admin", return_value=None):
        assert aw_mod.is_elevated_admin(None, "admin", uuid.uuid4()) is True
        assert aw_mod.is_elevated_admin(None, "user", uuid.uuid4()) is False
