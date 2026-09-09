"""Agent tool allowlists — no shared leaks, expected counts."""

from __future__ import annotations

import pytest

from apps.backend.domain.agent_runtime.registry import get_agent_registry

# agent_id -> (expected_count, must_include, must_exclude)
# +5 session harness tools (goal_*/todo_*) on user-facing agents
_HARNESS = frozenset(
    {
        "goal_get",
        "goal_create",
        "goal_update",
        "todo_write",
        "todo_read",
        "plan_mode_set",
        "exit_plan_mode",
    }
)
EXPECTATIONS: dict[str, tuple[int, frozenset[str], frozenset[str]]] = {
    "general": (
        18,
        frozenset(
            {
                "delegate",
                "catalog",
                "bind",
                "env_bindings",
                "save_user_secret",
                "request_user_secret",
                "secrets_help",
                "register_secrets",
            }
        )
        | _HARNESS,
        frozenset({"bash", "deferred_wait"}),
    ),
    "math": (11, frozenset({"math_eval", "math_percentage", "math_convert_units", "math_statistics"}) | _HARNESS, frozenset({"deferred_wait"})),
    "creative": (9, frozenset({"build"}) | _HARNESS, frozenset({"deferred_wait"})),
    "research": (24, frozenset({"web_search.search", "rag_search"}) | _HARNESS, frozenset({"bash"})),
    "communications": (17, frozenset({"send", "messaging.send"}) | _HARNESS, frozenset({"bash"})),
    "media": (20, frozenset({"media_list"}) | _HARNESS, frozenset({"dashboard.read"})),
    "integrations": (13, frozenset({"call", "summarize"}) | _HARNESS, frozenset({"git_push"})),
    "outdoor": (15, frozenset({"bite_index"}) | _HARNESS, frozenset({"bash"})),
    "lifestyle": (11, frozenset({"forecast", "current_time"}) | _HARNESS, frozenset({"bash"})),
    "dashboard": (34, frozenset({"dashboard.read", "propose_layouts"}) | _HARNESS, frozenset({"media_list", "git_push"})),
    "coding": (
        51,
        frozenset({"bash", "repository.write_file", "environment", "env_bindings"}) | _HARNESS,
        frozenset({"delegate", "start", "deferred_wait", "todo"}),
    ),
    "coding_plan": (
        26,
        frozenset({"repository.read_file", "environment"}) | _HARNESS,
        frozenset({"bash", "deferred_wait", "todo"}),
    ),
    "security_auditor": (
        37,
        frozenset({"start", "deferred_wait", "goal_create", "todo_write", "todo_read"}),
        frozenset({"bash", "delegate", "todo", "exit_plan_mode"}),
    ),
}


@pytest.mark.parametrize("agent_id", sorted(EXPECTATIONS))
def test_agent_tool_allowlist(agent_id: str) -> None:
    reg = get_agent_registry()
    ag = reg.get_agent(agent_id)
    assert ag is not None, agent_id
    names = frozenset(ag.get("tool_names") or [])
    count, must_have, must_not = EXPECTATIONS[agent_id]
    assert len(names) == count, (agent_id, sorted(names))
    assert must_have <= names, (agent_id, must_have - names)
    assert not (must_not & names), (agent_id, must_not & names)
