"""Unit tests for benchmark stats aggregation."""

from __future__ import annotations

from apps.backend.infrastructure.benchmarks.benchmark_stats import aggregate_benchmark_stats


def _run(
    run_id: str,
    suite: str,
    results: list[dict],
) -> dict:
    return {
        "id": run_id,
        "suite": suite,
        "status": "completed",
        "report_json": {"results": results},
    }


def _result(
    scenario_id: str,
    *,
    catalog: str = "provider_2",
    model: str = "qwen2.5:3b",
    label: str = "ollama",
    passed: bool = True,
    skipped: bool = False,
    latency_ms: float = 1000.0,
    score: float = 1.0,
) -> dict:
    return {
        "scenario_id": scenario_id,
        "catalog_owned_by": catalog,
        "model": model,
        "profile_label": label,
        "passed": passed,
        "skipped": skipped,
        "latency_ms": latency_ms,
        "score": score,
    }


def test_aggregate_groups_by_provider_and_model() -> None:
    runs = [
        _run(
            "r1",
            "smoke",
            [
                _result("S1", latency_ms=2000),
                _result("S2", latency_ms=3000),
            ],
        ),
        _run(
            "r2",
            "smoke",
            [
                _result("S1", latency_ms=4000, passed=False),
                _result("S2", latency_ms=5000),
            ],
        ),
        _run(
            "r2b",
            "smoke",
            [
                _result("S1", catalog="provider_1", model="qwen.gguf", label="llama.cpp", latency_ms=800),
                _result("S2", catalog="provider_1", model="qwen.gguf", label="llama.cpp", latency_ms=900),
            ],
        ),
    ]
    out = aggregate_benchmark_stats(runs)
    assert out["meta"]["run_count"] == 3
    assert out["meta"]["result_count"] == 6
    assert len(out["models"]) == 2

    ollama = next(m for m in out["models"] if m["model"] == "qwen2.5:3b")
    assert ollama["runs"] == 2
    assert ollama["samples"] == 4
    assert ollama["passed"] == 3
    assert ollama["pass_rate"] == 0.75
    assert ollama["avg_latency_ms"] == 3500.0

    llama = next(m for m in out["models"] if m["catalog_owned_by"] == "provider_1")
    assert llama["pass_rate"] == 1.0
    assert llama["avg_latency_ms"] == 850.0


def test_aggregate_suite_filter() -> None:
    runs = [
        _run("r1", "smoke", [_result("S1")]),
        _run("r2", "workspace", [_result("W1")]),
    ]
    out = aggregate_benchmark_stats(runs, suite_filter="workspace")
    assert out["meta"]["run_count"] == 1
    assert out["meta"]["suite_filter"] == "workspace"
    assert len(out["by_scenario"]) == 1
    assert out["by_scenario"][0]["scenario_id"] == "W1"


def test_by_scenario_ranks_fastest_and_best_pass() -> None:
    runs = [
        _run(
            "r1",
            "smoke",
            [
                _result("S2", catalog="provider_1", model="a", latency_ms=500, passed=True),
                _result("S2", catalog="provider_2", model="b", latency_ms=2000, passed=False),
                _result("S2", catalog="provider_2", model="c", latency_ms=1500, passed=True),
            ],
        ),
    ]
    out = aggregate_benchmark_stats(runs, badge_min_samples=1)
    s2 = next(s for s in out["by_scenario"] if s["scenario_id"] == "S2")
    assert s2["fastest"]["model"] == "a"
    assert s2["best_pass"]["model"] in ("a", "c")
    assert len(s2["models"]) == 3
    assert s2["models"][0]["pass_rate"] >= s2["models"][-1]["pass_rate"]


def test_fastest_ignores_fast_failures_with_zero_pass_rate() -> None:
    runs = [
        _run(
            "r1",
            "full",
            [
                _result("S1", catalog="provider_2", model="fast-fail", latency_ms=800, passed=False),
                _result("S1", catalog="provider_2", model="slow-pass", latency_ms=12000, passed=True),
            ],
        ),
    ]
    out = aggregate_benchmark_stats(runs, badge_min_samples=1, fastest_min_pass_rate=0.0)
    s1 = next(s for s in out["by_scenario"] if s["scenario_id"] == "S1")
    assert s1["fastest"]["model"] == "slow-pass"
    assert s1["best_pass"]["model"] == "slow-pass"


def test_best_pass_requires_badge_min_samples() -> None:
    runs = [
        _run(
            "r1",
            "smoke",
            [_result("S1", catalog="provider_1", model="solo", latency_ms=1000, passed=True)],
        ),
    ]
    out = aggregate_benchmark_stats(runs, badge_min_samples=2)
    s1 = next(s for s in out["by_scenario"] if s["scenario_id"] == "S1")
    assert s1["best_pass"] is None
    assert s1["fastest"] is None


def test_skipped_results_counted_separately() -> None:
    runs = [
        _run(
            "r1",
            "smoke",
            [
                _result("S1", skipped=True),
                _result("S2", passed=True),
            ],
        ),
    ]
    out = aggregate_benchmark_stats(runs)
    model = out["models"][0]
    assert model["skipped"] == 1
    assert model["samples"] == 1
    assert model["pass_rate"] == 1.0
