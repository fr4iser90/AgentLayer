"""Pytest live gate for agent LLM benchmarks (see ``pytest -m benchmark``)."""

from __future__ import annotations

import os

from tests.benchmarks.agent.harness import BenchRunReport, load_bench_env, repo_root


def bench_live_enabled() -> bool:
    return (os.environ.get("AGENT_BENCH_LIVE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def has_bench_llm_config() -> bool:
    load_bench_env()
    for n in range(1, 17):
        base = (os.environ.get(f"AGENT_BENCH_LLM_{n}_BASE_URL") or "").strip()
        catalog = (os.environ.get(f"AGENT_BENCH_LLM_{n}_CATALOG") or "").strip()
        model = (os.environ.get(f"AGENT_BENCH_LLM_{n}_MODEL") or "").strip()
        if base and model:
            return True
        if catalog:
            return True
    return False


def skip_reason_if_not_live() -> str | None:
    if not bench_live_enabled():
        return (
            "Set AGENT_BENCH_LIVE=1 (pytest -m benchmark tests/benchmarks/agent/test_live_benchmark.py). "
            "LLM endpoints: Admin → Interfaces, or optional AGENT_BENCH_LLM_* in .env"
        )
    return None


def assert_benchmark_report(report: BenchRunReport, *, suite: str) -> None:
    executed = [r for r in report.results if not r.skipped]
    skipped = [r for r in report.results if r.skipped]
    failed = [r for r in executed if not r.passed]
    if not executed:
        raise AssertionError(
            f"{suite}: no scenarios executed ({len(skipped)} skipped) — check fixtures/credentials"
        )
    if failed:
        lines = [
            f"  {r.scenario_id} @ {r.profile_label}: {r.failure_reason or r.error or 'failed'}"
            for r in failed
        ]
        raise AssertionError(
            f"{suite} benchmark failed ({len(failed)}/{len(executed)}), "
            f"{len(skipped)} skipped:\n" + "\n".join(lines)
        )


def manifest_path(name: str) -> os.PathLike[str]:
    return repo_root() / "benchmarks" / "manifests" / name
