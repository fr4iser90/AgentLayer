"""Live agent LLM benchmarks — requires running AgentLayer + .env credentials.

Run:
  export AGENT_BENCH_LIVE=1
  ./scripts/run-agent-benchmark-pytest.sh
  # or: pytest -m benchmark tests/benchmarks/agent/test_live_benchmark.py -v
"""

from __future__ import annotations

import os

import pytest

from tests.benchmarks.agent.harness import run_benchmark, write_report
from tests.benchmarks.agent.live_gate import assert_benchmark_report, manifest_path

pytestmark = pytest.mark.benchmark


def _profile_filter() -> str | None:
    raw = (os.environ.get("AGENT_BENCH_PROFILES") or "").strip()
    if not raw:
        return None
    return raw.split(",")[0].strip() or None


def _maybe_write_report(report, subdir: str) -> None:
    if (os.environ.get("AGENT_BENCH_PYTEST_WRITE_JSON") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return
    from tests.benchmarks.agent.harness import repo_root

    out = repo_root() / "benchmarks" / "results" / "pytest" / subdir
    write_report(report, out)


def test_smoke_suite(bench_live: None) -> None:
    report = run_benchmark(
        manifest_path=manifest_path("smoke.yaml"),
        profile_filter=_profile_filter(),
    )
    _maybe_write_report(report, "smoke")
    assert_benchmark_report(report, suite="smoke")


def test_workspace_w1_git_readme(bench_live: None) -> None:
    report = run_benchmark(
        manifest_path=manifest_path("workspace.yaml"),
        scenario_filter=["W1_git_readme_no_index"],
        profile_filter=_profile_filter(),
    )
    _maybe_write_report(report, "workspace-w1")
    assert_benchmark_report(report, suite="workspace-w1")
