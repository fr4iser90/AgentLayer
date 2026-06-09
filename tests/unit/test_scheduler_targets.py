"""Scheduler execution_target = registry agent ids."""

from apps.backend.domain.scheduler_targets import (
    EXECUTION_CODING,
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
    assert normalize_execution_target("coding") == EXECUTION_CODING


def test_valid_schedulable_agents() -> None:
    assert is_valid_execution_target("general")
    assert is_valid_execution_target("coding")
    assert is_valid_execution_target("coding_plan")
    assert is_valid_execution_target("security_auditor")
    assert not is_valid_execution_target("coding_agent")
    assert not is_valid_execution_target("operator")
    assert not is_valid_execution_target("bogus")


def test_unknown_target_error_lists_agents() -> None:
    err = execution_target_error("bogus")
    assert "general" in err
    assert "coding" in err


def test_workspace_flag() -> None:
    assert not agent_requires_workspace_for_target("general")
    assert agent_requires_workspace_for_target("coding")


def test_execution_target_catalog_matches_registry() -> None:
    cat = execution_target_catalog()
    values = {row["value"] for row in cat}
    assert values == set(schedulable_agent_ids())
    assert EXECUTION_GENERAL in values
    assert EXECUTION_CODING in values
    assert "operator" not in values
    assert all(row.get("agent_id") == row["value"] for row in cat)
    coding_row = next(r for r in cat if r["value"] == "coding")
    assert coding_row.get("requires_workspace") is True
