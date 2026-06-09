"""Unit tests for benchmark live-gate helpers (no server)."""

from __future__ import annotations

import pytest

from tests.benchmarks.agent.harness import BenchRunReport, ScenarioResult
from tests.benchmarks.agent.live_gate import assert_benchmark_report, bench_live_enabled


def test_bench_live_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_BENCH_LIVE", raising=False)
    assert bench_live_enabled() is False


def test_bench_live_enabled_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_BENCH_LIVE", "1")
    assert bench_live_enabled() is True


def test_assert_report_passes_when_all_ok() -> None:
    report = BenchRunReport(
        run_id="test",
        started_at="2026-01-01T00:00:00Z",
        base_url="http://127.0.0.1:8088",
        git_sha="abc",
        tier_max=1,
        manifest_path="smoke.yaml",
        resource_prefix="bench-test-",
        results=[
            ScenarioResult(
                run_id="test",
                scenario_id="S1_tool_catalog",
                profile_label="ollama",
                model="qwen",
                catalog_owned_by="provider_1",
                agent_id="general",
                passed=True,
                score=1.0,
                failure_reason=None,
                latency_ms=100.0,
                prompt_tokens=1,
                completion_tokens=1,
                tool_call_count=1,
                tool_names=["catalog"],
                agent_run_id="run-1",
                assistant_excerpt="ok",
            )
        ],
    )
    assert_benchmark_report(report, suite="smoke")


def test_assert_report_fails_on_failed_scenario() -> None:
    report = BenchRunReport(
        run_id="test",
        started_at="2026-01-01T00:00:00Z",
        base_url="http://127.0.0.1:8088",
        git_sha="abc",
        tier_max=1,
        manifest_path="smoke.yaml",
        resource_prefix="bench-test-",
        results=[
            ScenarioResult(
                run_id="test",
                scenario_id="S2_simple_chat",
                profile_label="ollama",
                model="qwen",
                catalog_owned_by="provider_1",
                agent_id="general",
                passed=False,
                score=0.0,
                failure_reason="wrong answer",
                latency_ms=100.0,
                prompt_tokens=1,
                completion_tokens=1,
                tool_call_count=0,
                tool_names=[],
                agent_run_id="run-1",
                assistant_excerpt="41",
            )
        ],
    )
    with pytest.raises(AssertionError, match="S2_simple_chat"):
        assert_benchmark_report(report, suite="smoke")
