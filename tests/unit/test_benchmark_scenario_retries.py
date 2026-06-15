"""Benchmark scenario failure retries (admin run limits)."""

from __future__ import annotations

from tests.benchmarks.agent.harness import ScenarioResult, _attach_scenario_retry_metrics


def _minimal_result(*, passed: bool) -> ScenarioResult:
    return ScenarioResult(
        run_id="r1",
        scenario_id="S1_tool_catalog",
        profile_label="OLLAMA",
        model="nemotron",
        catalog_owned_by="provider_2",
        agent_id="general",
        passed=passed,
        score=1.0 if passed else 0.0,
        failure_reason=None if passed else "rubric failed",
        latency_ms=1.0,
        prompt_tokens=None,
        completion_tokens=None,
        tool_call_count=0,
        tool_names=[],
        agent_run_id=None,
        assistant_excerpt="",
    )


def test_attach_retry_metrics_skipped_when_single_attempt() -> None:
    result = _minimal_result(passed=False)
    out = _attach_scenario_retry_metrics(
        result,
        attempt=1,
        attempts_max=1,
        prior_failure_reasons=["first fail"],
        attempt_history=[],
    )
    assert out.run_metrics is None


def test_attach_retry_metrics_on_pass_after_retry() -> None:
    result = _minimal_result(passed=True)
    hist = [
        {"attempt": 1, "passed": False, "failure_reason": "no catalog"},
        {"attempt": 2, "passed": True, "failure_reason": None},
    ]
    out = _attach_scenario_retry_metrics(
        result,
        attempt=2,
        attempts_max=3,
        prior_failure_reasons=["no catalog tool call"],
        attempt_history=hist,
    )
    assert out.run_metrics is not None
    assert out.run_metrics["attempt"] == 2
    assert out.run_metrics["attempts_max"] == 3
    assert out.run_metrics["prior_failure_reasons"] == ["no catalog tool call"]
    assert out.run_metrics["attempt_history"] == hist
    assert out.run_metrics["pass_at_1"] is False


def test_attach_retry_metrics_on_final_failure() -> None:
    result = _minimal_result(passed=False)
    hist = [
        {"attempt": 1, "passed": False},
        {"attempt": 2, "passed": False},
        {"attempt": 3, "passed": False},
    ]
    out = _attach_scenario_retry_metrics(
        result,
        attempt=3,
        attempts_max=3,
        prior_failure_reasons=["fail one", "fail two"],
        attempt_history=hist,
    )
    assert out.run_metrics is not None
    assert out.run_metrics["attempt"] == 3
    assert out.run_metrics["prior_failure_reasons"] == ["fail one", "fail two"]
    assert len(out.run_metrics["attempt_history"]) == 3
