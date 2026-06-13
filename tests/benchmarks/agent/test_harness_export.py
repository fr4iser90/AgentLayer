"""Harness export rows and rubric vs transport failure split."""

from __future__ import annotations

from tests.benchmarks.agent.harness import (
    BenchRunReport,
    ScenarioResult,
    failure_export_row,
    failures_from_report,
    scenario_export_row,
)
from tests.benchmarks.agent.rubrics import evaluate_rubric


def test_rubric_evaluated_without_transport_error() -> None:
    substantive = evaluate_rubric(
        "d2_layout_patch",
        content="",
        tool_names=["create_dashboard"],
        error=None,
        dashboard_state={"ui_layout": {}, "data": {}},
    )
    with_transport = evaluate_rubric(
        "d2_layout_patch",
        content="",
        tool_names=["create_dashboard"],
        error="scenario timeout after 360s",
        dashboard_state={"ui_layout": {}, "data": {}},
    )
    assert substantive.passed is False
    assert substantive.failure_reason
    assert with_transport.failure_reason == "scenario timeout after 360s"


def test_scenario_export_row_splits_transport_and_rubric() -> None:
    row = scenario_export_row(
        ScenarioResult(
            run_id="r1",
            scenario_id="D2_layout_patch",
            profile_label="LLAMA.CPP",
            model="qwen",
            catalog_owned_by="env",
            agent_id="general",
            passed=False,
            score=0.0,
            failure_reason="scenario timeout after 360s",
            rubric_failure_reason="no markdown block with dataPath notes",
            transport_error="scenario timeout after 360s",
            latency_ms=360000.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=16,
            tool_names=["create_dashboard"],
            agent_run_id="abc",
            assistant_excerpt="",
            run_metrics={
                "llm_round_count": 16,
                "bench_diagnostics": {
                    "insights": ["create_dashboard repeated 12× with empty args"],
                },
            },
        )
    )
    assert row["transport_error"] == "scenario timeout after 360s"
    assert row["rubric_failure"] == "no markdown block with dataPath notes"
    assert "create_dashboard" in row["insights"]


def test_failure_export_row_includes_debug_fields() -> None:
    row = failure_export_row(
        ScenarioResult(
            run_id="r1",
            scenario_id="W1_git_readme_no_index",
            profile_label="LLAMA.CPP",
            model="qwen",
            catalog_owned_by="env",
            agent_id="general",
            passed=False,
            score=0.0,
            failure_reason="read_file not used",
            rubric_failure_reason="read_file not used",
            latency_ms=1000.0,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_count=2,
            tool_names=["workspace.create"],
            agent_run_id="run-abc",
            assistant_excerpt="Hello README line",
            run_metrics={
                "llm_round_count": 3,
                "bench_diagnostics": {
                    "session": {
                        "effective_agent_id": "general",
                        "forwarded_tool_count": 18,
                        "forwarded_tools": ["delegate", "workspace.create", "read_file"],
                    },
                    "tool_rounds": [
                        {
                            "name": "workspace.create",
                            "normalized_arguments": {"name": "bench-prefix-git"},
                        },
                        {"name": "delegate"},
                    ],
                    "event_counts": {"subagent_start_count": 1},
                    "ws_errors": [{"type": "agent.cancelled", "detail": "cancelled"}],
                    "insights": ["delegate repeated 2×"],
                },
            },
        ),
        resource_prefix="bench-prefix-",
    )
    assert row["agent_id"] == "general"
    assert row["effective_agent_id"] == "general"
    assert row["forwarded_tool_count"] == 18
    assert "delegate" in row["forwarded_tools"]
    assert row["assistant_excerpt"] == "Hello README line"
    assert row["expected_workspace_name"] == "bench-prefix-git"
    assert row["workspace_create_name"] == "bench-prefix-git"
    assert row["delegate_call_count"] == 1
    assert row["subagent_start_count"] == 1
    assert "cancelled" in row["ws_errors"]
    assert "report_summary" in row
    assert "report" in row
    assert isinstance(row["report"], dict)


def test_failures_from_report_excludes_passed_and_skipped() -> None:
    report = BenchRunReport(
        run_id="run-1",
        started_at="2026-01-01T00:00:00Z",
        base_url="http://localhost",
        git_sha=None,
        tier_max=3,
        manifest_path="manifest.yaml",
        resource_prefix="bench-prefix",
        results=[
            ScenarioResult(
                run_id="run-1",
                scenario_id="S1",
                profile_label="p1",
                model="m1",
                catalog_owned_by="env",
                agent_id="general",
                passed=True,
                score=1.0,
                failure_reason=None,
                latency_ms=1.0,
                prompt_tokens=None,
                completion_tokens=None,
                tool_call_count=1,
                tool_names=[],
                agent_run_id=None,
                assistant_excerpt="",
            ),
            ScenarioResult(
                run_id="run-1",
                scenario_id="S2",
                profile_label="p1",
                model="m1",
                catalog_owned_by="env",
                agent_id="general",
                passed=False,
                score=0.0,
                failure_reason="timeout",
                rubric_failure_reason="read_file not invoked",
                transport_error="timeout",
                latency_ms=2.0,
                prompt_tokens=None,
                completion_tokens=None,
                tool_call_count=0,
                tool_names=[],
                agent_run_id=None,
                assistant_excerpt="",
                skipped=True,
            ),
            ScenarioResult(
                run_id="run-1",
                scenario_id="S3",
                profile_label="p1",
                model="m1",
                catalog_owned_by="env",
                agent_id="general",
                passed=False,
                score=0.0,
                failure_reason="fail",
                latency_ms=3.0,
                prompt_tokens=None,
                completion_tokens=None,
                tool_call_count=0,
                tool_names=[],
                agent_run_id=None,
                assistant_excerpt="",
            ),
        ],
    )
    failures = failures_from_report(report)
    assert len(failures) == 1
    assert failures[0]["scenario_id"] == "S3"
