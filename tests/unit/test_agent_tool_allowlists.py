"""Agent tool allowlists — no shared leaks, expected counts."""

from __future__ import annotations

import pytest

from apps.backend.domain.agent_registry import get_agent_registry

# agent_id -> (expected_count, must_include, must_exclude)
EXPECTATIONS: dict[str, tuple[int, frozenset[str], frozenset[str]]] = {
    "general": (6, frozenset({"delegate", "catalog"}), frozenset({"bash", "deferred_wait"})),
    "math": (4, frozenset({"math_eval", "math_percentage", "math_convert_units", "math_statistics"}), frozenset({"deferred_wait"})),
    "creative": (2, frozenset({"build"}), frozenset({"deferred_wait"})),
    "research": (17, frozenset({"web_search.search", "rag_search"}), frozenset({"bash"})),
    "communications": (10, frozenset({"send", "messaging.send"}), frozenset({"bash"})),
    "media": (13, frozenset({"media_list"}), frozenset({"dashboard.read"})),
    "integrations": (6, frozenset({"call", "summarize"}), frozenset({"git_push"})),
    "outdoor": (8, frozenset({"bite_index"}), frozenset({"bash"})),
    "lifestyle": (4, frozenset({"forecast", "current_time"}), frozenset({"bash"})),
    "dashboard": (27, frozenset({"dashboard.read", "propose_layouts"}), frozenset({"media_list", "git_push"})),
    "coding": (43, frozenset({"bash", "repository.write_file"}), frozenset({"delegate", "start", "deferred_wait"})),
    "coding_plan": (19, frozenset({"repository.read_file"}), frozenset({"bash", "deferred_wait"})),
    "security_auditor": (33, frozenset({"start", "deferred_wait"}), frozenset({"bash", "delegate"})),
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
