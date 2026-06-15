"""Attempt history export rows."""

from __future__ import annotations

from tests.benchmarks.agent.harness import (
    ScenarioResult,
    pass_at_1_from_result,
    scenario_attempt_export_rows,
    scenario_export_row,
)


def test_scenario_export_row_includes_attempt_fields() -> None:
    row = scenario_export_row(
        ScenarioResult(
            run_id="r1",
            scenario_id="W1_git_readme_no_index",
            profile_label="OLLAMA",
            model="nemotron",
            catalog_owned_by="p2",
            agent_id="general",
            passed=True,
            score=1.0,
            failure_reason=None,
            latency_ms=1000.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=2,
            tool_names=["workspace.create", "delegate"],
            agent_run_id="run-1",
            assistant_excerpt="line",
            run_metrics={
                "attempt": 2,
                "attempts_max": 3,
                "pass_at_1": False,
                "prior_failure_reasons": ["missing delegate"],
            },
        )
    )
    assert row["attempt"] == 2
    assert row["attempts_max"] == 3
    assert row["pass_at_1"] is False
    assert "missing delegate" in row["prior_failure_reasons"]


def test_scenario_attempt_export_rows_one_per_history_entry() -> None:
    base = ScenarioResult(
        run_id="r1",
        scenario_id="W1_git_readme_no_index",
        profile_label="OLLAMA",
        model="nemotron",
        catalog_owned_by="p2",
        agent_id="general",
        passed=True,
        score=1.0,
        failure_reason=None,
        latency_ms=2000.0,
        prompt_tokens=None,
        completion_tokens=None,
        tool_call_count=2,
        tool_names=["delegate"],
        agent_run_id="run-2",
        assistant_excerpt="ok",
        run_metrics={
            "attempt": 2,
            "attempts_max": 2,
            "pass_at_1": False,
            "attempt_history": [
                {
                    "attempt": 1,
                    "passed": False,
                    "failure_reason": "no delegate",
                    "tool_call_count": 1,
                    "tool_names": ["workspace.create"],
                    "latency_ms": 1000.0,
                    "run_metrics": {"llm_round_count": 2},
                },
                {
                    "attempt": 2,
                    "passed": True,
                    "failure_reason": None,
                    "tool_call_count": 2,
                    "tool_names": ["workspace.create", "delegate"],
                    "latency_ms": 2000.0,
                    "run_metrics": {"llm_round_count": 2},
                },
            ],
        },
    )
    rows = scenario_attempt_export_rows(base)
    assert len(rows) == 2
    assert rows[0]["attempt"] == 1
    assert rows[0]["passed"] is False
    assert rows[1]["attempt"] == 2
    assert rows[1]["passed"] is True
    assert rows[1]["attempt_is_final"] is True
    assert pass_at_1_from_result(base) is False
