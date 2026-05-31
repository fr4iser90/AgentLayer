"""Tests for agent tool allowlists (``AGENT_TOOL_DOMAINS`` + ``AGENT_TOOL_CAPABILITY_ANY``)."""

from __future__ import annotations

from apps.backend.domain.agent_registry import _tools_for_capabilities_any, _tools_for_domains


def _repo(names: list[str], base: str) -> bool:
    """True if ``base`` or ``repository.<base>`` is in resolved tool names."""
    return base in names or f"repository.{base}" in names


def test_tools_for_domains_matches_tool_domain_metadata() -> None:
    names = ["repository.read_file", "read_file", "bash", "mail.search"]
    out = _tools_for_domains(["files"], names, include_introspection=False)
    assert out == ["read_file"]


def test_tools_for_capabilities_resolves_coding_read() -> None:
    names = ["repository.read_file", "bash", "write_file", "git_read"]
    out = _tools_for_capabilities_any(["coding.read"], names)
    assert "repository.read_file" in out
    assert "git_read" in out
    assert "bash" not in out
    assert "write_file" not in out


def test_coding_agent_uses_domains_only() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    names = a["tool_names"]
    assert _repo(names, "read_file")
    assert "project_explain" in names
    assert "save_user_secret" in names
    assert "workspace.list" in names
    assert "git_read" in names
    assert "git_push" in names
    assert "list_available_tools" not in names
    assert "github" in (a.get("tool_domains") or [])


def test_creative_and_dashboard_agents() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    c = reg.get_agent("creative")
    assert c is not None
    assert "build" in c["tool_names"]
    assert "bash" not in c["tool_names"]

    d = reg.get_agent("dashboard")
    assert d is not None
    assert "boards" in d["tool_names"] or "dashboard.read" in d["tool_names"]
    assert "bash" not in d["tool_names"]


def test_general_agent_slimmer_no_github_domain() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("general")
    assert a is not None
    assert "github" not in (a.get("tool_domains") or [])
    assert "shopping" not in (a.get("tool_domains") or [])
    assert "creative" not in (a.get("tool_domains") or [])
    assert "calendar" not in (a.get("tool_domains") or [])
    assert "rss" not in (a.get("tool_domains") or [])
    assert "tasks" not in (a.get("tool_domains") or [])
    assert _repo(a["tool_names"], "read_file")
    assert "git_read" in a["tool_names"]  # via coding.read capability
    assert "bash" not in a["tool_names"]
    assert "git_push" not in a["tool_names"]  # github domain only on coding
    assert "task" not in a["tool_names"]
    assert "todo" not in a["tool_names"]
    assert "rss.boards" not in a["tool_names"]
    assert "tasks.boards" not in a["tool_names"]


def test_coding_agent_has_workspace_repository_and_delegate_domains() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    domains = a.get("tool_domains") or []
    assert "workspace" in domains
    assert "repository" in domains
    assert "delegate" in domains
    assert "coding" not in domains
    assert "task" in a["tool_names"]
    assert "todo" in a["tool_names"]


def test_operator_agent_matches_capabilities() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("operator")
    assert a is not None
    names = a["tool_names"]
    assert "settings_get" in names
    assert "rag_search" in names
    assert "scheduler.list" in names


def test_security_auditor_agent_resolves_domains_and_rag_capability() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("security_auditor")
    assert a is not None
    names = a["tool_names"]
    assert _repo(names, "read_file")
    assert "project_explain" in names
    assert "rag_search" in names
    assert "save_user_secret" in names
    for denied in ("bash", "write_file", "edit", "apply_patch", "git_push"):
        assert denied not in names


def test_coding_plan_agent_read_only_via_capabilities() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("coding_plan")
    assert a is not None
    names = a["tool_names"]
    assert _repo(names, "read_file")
    assert _repo(names, "search")
    assert "git_read" in names
    assert "workspace.list" in names
    for denied in (
        "bash",
        "git_sync",
        "git_push",
        "write_file",
        "edit",
        "replace",
        "apply_patch",
    ):
        assert denied not in names


def test_general_agent_no_bash_uses_capabilities_for_coding_read() -> None:
    from apps.backend.core.config import PLUGINS_DIR

    general_yaml = PLUGINS_DIR / "agents" / "general" / "agent.yaml"
    assert general_yaml.is_file()
    text = general_yaml.read_text(encoding="utf-8")
    assert "tool_domains:" in text
    assert "tool_capability_any:" in text

    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("general")
    assert a is not None
    assert a.get("source_kind") == "yaml"
    assert a.get("tool_domains")
    assert a.get("tool_capability_any")
    assert _repo(a["tool_names"], "read_file")
    assert "bash" not in a["tool_names"]


def test_agents_loaded_from_yaml_directories() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    for aid in ("coding_plan", "coding", "operator", "security_auditor", "general", "creative", "dashboard"):
        a = reg.get_agent(aid)
        assert a is not None, aid
        assert a.get("source_kind") == "yaml"
        assert a.get("source_path", "").endswith("agent.yaml")
        assert a.get("system_prompt"), aid


def test_missing_tools_not_in_allowlist() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    reg = get_agent_registry()
    reg.ensure_loaded()
    reg._agents["_test_phantom"] = {
        "id": "_test_phantom",
        "tool_domains": [],
        "tool_capability_any": ["this.capability.does.not.exist"],
        "tool_include_introspection": False,
    }
    a = reg.get_agent("_test_phantom")
    assert a is not None
    assert a["tool_names"] == []


def test_agent_behavior_flags_come_from_plugins_not_ids() -> None:
    from apps.backend.domain.agent import _agent_behavior_flags

    c = _agent_behavior_flags("coding")
    assert c["coding_tools_permission_ask"] is False
    assert c["strict_workspace"] is False
    assert c["tool_discipline_preset"] == "coding_build"

    p = _agent_behavior_flags("coding_plan")
    assert p["strict_workspace"] is True
    assert p["coding_tools_permission_ask"] is False
    assert p["tool_discipline_preset"] == "coding_plan"

    s = _agent_behavior_flags("security_auditor")
    assert s["strict_workspace"] is True
