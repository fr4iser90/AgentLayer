"""Scheduler execution_target = registry agent ids."""

import uuid
from unittest.mock import patch

from apps.backend.domain.scheduling.targets import (
    EXECUTION_CODING,
    EXECUTION_GENERAL,
    agent_requires_workspace_for_target,
    execution_target_catalog,
    execution_target_error,
    is_valid_execution_target,
    normalize_execution_target,
    schedulable_agent_ids,
    schedule_permission_error,
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


def test_execution_target_catalog_unfiltered_without_caller() -> None:
    """Admin surfaces keep the full registry view."""
    cat = execution_target_catalog(user_role="admin")
    assert {row["value"] for row in cat} == set(schedulable_agent_ids())


def test_execution_target_catalog_filters_by_caller_access() -> None:
    all_ids = schedulable_agent_ids()
    assert all_ids
    keep = all_ids[0]

    def fake(user_role, agent_id, *, tenant_id=None, user_id=None):
        return (True, "") if agent_id == keep else (False, "denied")

    with patch(
        "apps.backend.domain.agent_runtime.access.user_may_invoke_agent",
        side_effect=fake,
    ):
        cat = execution_target_catalog(
            user_role="user", user_id=uuid.uuid4(), tenant_id=1
        )
    assert [row["value"] for row in cat] == [keep]


def test_execution_target_catalog_passes_caller_through() -> None:
    uid = uuid.uuid4()
    seen: list[tuple] = []

    def fake(user_role, agent_id, *, tenant_id=None, user_id=None):
        seen.append((agent_id, tenant_id, user_id))
        return True, ""

    with patch(
        "apps.backend.domain.agent_runtime.access.user_may_invoke_agent",
        side_effect=fake,
    ):
        execution_target_catalog(user_role="user", user_id=uid, tenant_id=7)

    assert seen
    assert {tid for _aid, tid, _uid in seen} == {7}
    assert {u for _aid, _tid, u in seen} == {uid}


def test_schedule_permission_error_denies_when_access_layer_denies() -> None:
    """min_role alone is not the whole answer — a denied policy must reject the schedule."""
    with patch(
        "apps.backend.domain.agent_runtime.access.user_may_invoke_agent",
        return_value=(False, "This agent is not enabled for your organization."),
    ):
        err = schedule_permission_error(
            user_role="user",
            execution_target=EXECUTION_GENERAL,
            user_id=uuid.uuid4(),
            tenant_id=3,
        )
    assert err is not None
    assert "not available for your account" in err
    assert "not enabled for your organization" in err


def test_schedule_permission_error_passes_tenant_and_user_to_access_layer() -> None:
    uid = uuid.uuid4()
    seen: dict[str, object] = {}

    def fake(user_role, agent_id, *, tenant_id=None, user_id=None):
        seen["role"] = user_role
        seen["agent_id"] = agent_id
        seen["tenant_id"] = tenant_id
        seen["user_id"] = user_id
        return True, ""

    with patch(
        "apps.backend.domain.agent_runtime.access.user_may_invoke_agent",
        side_effect=fake,
    ):
        assert (
            schedule_permission_error(
                user_role="user",
                execution_target=EXECUTION_GENERAL,
                user_id=uid,
                tenant_id=9,
            )
            is None
        )

    assert seen == {"role": "user", "agent_id": EXECUTION_GENERAL, "tenant_id": 9, "user_id": uid}
