"""
Retrieval layer benchmarks: Hit@k, tool-call count, latency.

CI (default): fixture mini-workspace, real ``search`` / ``retrieve_context``.
Optional live: ``RETRIEVAL_BENCH_LIVE=1`` also runs cases against the AgentLayer repo
(requires Qdrant + embeddings for semantic/doc cases).

Run:
  python -m unittest tests.test_retrieval_benchmark -v
  python scripts/run_retrieval_benchmark.py
  RETRIEVAL_BENCH_LIVE=1 python scripts/run_retrieval_benchmark.py --live
"""

from __future__ import annotations

import os
import unittest

from tests.benchmarks.retrieval.cases import (
    FIXTURE_CASES,
    cases_for_run,
    fixture_workspace_path,
    repo_root,
)
from tests.benchmarks.retrieval.harness import compare_strategies, run_suite

# Minimum Hit@k for fixture suite (grep-heavy). Tune when adding RRF/fusion.
FIXTURE_MIN_HIT_RATE = 0.8


class TestRetrievalBenchmarkFixture(unittest.TestCase):
    """Deterministic benchmark on ``tests/benchmarks/fixtures/retrieval_mini``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = str(fixture_workspace_path())
        cls.cases = [c for c in FIXTURE_CASES if not c.live_only]

    def test_unified_hit_rate_meets_baseline(self) -> None:
        report = run_suite(self.cases, strategy="unified", workspace_path=self.workspace)
        self.assertGreaterEqual(
            report.hit_rate,
            FIXTURE_MIN_HIT_RATE,
            msg=_format_failures(report),
        )

    def test_unified_beats_separate_on_tool_calls(self) -> None:
        unified = run_suite(self.cases, strategy="unified", workspace_path=self.workspace)
        separate = run_suite(self.cases, strategy="separate", workspace_path=self.workspace)
        self.assertLess(unified.mean_tool_calls, separate.mean_tool_calls)
        self.assertEqual(unified.mean_tool_calls, 1.0)

    def test_unified_latency_not_worse_than_separate_sum(self) -> None:
        """Unified should not be dramatically slower than separate for the same work."""
        unified = run_suite(self.cases, strategy="unified", workspace_path=self.workspace)
        separate = run_suite(self.cases, strategy="separate", workspace_path=self.workspace)
        # Allow 2x slack (sequential sub-calls vs one JSON bundle overhead).
        self.assertLessEqual(
            unified.p95_latency_ms,
            max(separate.p95_latency_ms * 2.0, 500.0),
        )

    def test_compare_strategies_report_shape(self) -> None:
        reports = compare_strategies(self.cases, workspace_path=self.workspace)
        self.assertIn("unified", reports)
        self.assertIn("separate", reports)
        for key, rep in reports.items():
            self.assertEqual(rep.strategy, key)
            self.assertEqual(rep.case_count, len(self.cases))
            d = rep.to_dict()
            self.assertIn("hit_at_k", d)
            self.assertIn("mean_tool_calls", d)


def _format_failures(report) -> str:
    lines = [f"hit_rate={report.hit_rate} (min {FIXTURE_MIN_HIT_RATE})"]
    for c in report.cases:
        if not c.hit:
            lines.append(
                f"  MISS {c.case_id}: needles not in top-{c.k} "
                f"(candidates={c.candidate_count}, err={c.error})"
            )
    return "\n".join(lines)


@unittest.skipUnless(
    os.environ.get("RETRIEVAL_BENCH_LIVE", "").strip().lower() in ("1", "true", "yes"),
    "set RETRIEVAL_BENCH_LIVE=1 to run against the AgentLayer repo",
)
class TestRetrievalBenchmarkLive(unittest.TestCase):
    """Live benchmark on the checkout (semantic needs Qdrant + index)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = str(repo_root())
        cls.cases = cases_for_run(live=True)

    def test_live_compare_strategies(self) -> None:
        reports = compare_strategies(self.cases, workspace_path=self.workspace)
        u = reports["unified"]
        s = reports["separate"]
        print("\n--- LIVE retrieval benchmark ---")
        print(f"workspace: {self.workspace}")
        print(f"unified:  Hit@{u.cases[0].k if u.cases else 8}={u.hit_rate} tool_calls={u.mean_tool_calls} p50={u.p50_latency_ms}ms")
        print(f"separate: Hit@{s.cases[0].k if s.cases else 8}={s.hit_rate} tool_calls={s.mean_tool_calls} p50={s.p50_latency_ms}ms")
        for c in u.cases:
            mark = "OK" if c.hit else "MISS"
            print(f"  [{mark}] {c.case_id} rank={c.first_rank} sources={c.hit_sources} err={c.error}")
        self.assertGreater(u.case_count, 0)


if __name__ == "__main__":
    unittest.main()
