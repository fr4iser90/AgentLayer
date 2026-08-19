"""Scheduler execution_target = registry agent ids."""

from apps.backend.domain.scheduling.targets import (
    EXECUTION_GENERAL,
    agent_requires_workspace_for_target,
    execution_target_catalog,
    execution_target_error,
    is_valid_execution_target,
    normalize_execution_target,
    schedulable_agent_ids,
)


def test_normalize_agent_ids() -> None:
    assert normalize_execution_target("general") == EXECUTION_GENERAL
    assert normalize_execution_target("GENERAL") == EXECUTION_GENERAL
    assert normalize_execution_target("research") == "research"


def test_valid_schedulable_agents() -> None:
    assert is_valid_execution_target("general")
    assert is_valid_execution_target("research")
    assert not is_valid_execution_target("coding")
    assert not is_valid_execution_target("coding_plan")
    assert not is_valid_execution_target("security_auditor")
    assert not is_valid_execution_target("coding_agent")
    assert not is_valid_execution_target("operator")
    assert not is_valid_execution_target("bogus")


def test_unknown_target_error_lists_agents() -> None:
    err = execution_target_error("bogus")
    assert "general" in err
    assert "research" in err


def test_workspace_flag() -> None:
    assert not agent_requires_workspace_for_target("general")
    assert not agent_requires_workspace_for_target("research")


def test_execution_target_catalog_matches_registry() -> None:
    cat = execution_target_catalog()
    values = {row["value"] for row in cat}
    assert values == set(schedulable_agent_ids())
    assert EXECUTION_GENERAL in values
    assert "coding" not in values
    assert "operator" not in values
    assert all(row.get("agent_id") == row["value"] for row in cat)
