#!/usr/bin/env python3
"""
Run retrieval benchmarks and print a summary table (JSON optional).

Examples:
  python scripts/run_retrieval_benchmark.py
  python scripts/run_retrieval_benchmark.py --json-out /tmp/retrieval_bench.json
  RETRIEVAL_BENCH_LIVE=1 python scripts/run_retrieval_benchmark.py --live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.benchmarks.retrieval.cases import cases_for_run, fixture_workspace_path, repo_root
from tests.benchmarks.retrieval.harness import compare_strategies


def _print_report(label: str, report) -> None:
    print(f"\n== {label} ==")
    print(f"  workspace:     {report.workspace_path}")
    print(f"  cases:         {report.case_count}")
    print(f"  Hit@k:         {report.hit_at_k:.2%} ({report.hits}/{report.case_count})")
    print(f"  tool_calls:    {report.mean_tool_calls:.2f} mean per query")
    print(f"  latency p50:   {report.p50_latency_ms:.1f} ms")
    print(f"  latency p95:   {report.p95_latency_ms:.1f} ms")
    for c in report.cases:
        mark = "hit" if c.hit else "MISS"
        print(
            f"    [{mark}] {c.case_id}: rank={c.first_rank} "
            f"candidates={c.candidate_count} tools={c.tool_calls} "
            f"{c.latency_ms:.0f}ms sources={c.hit_sources or '-'}"
            + (f" err={c.error}" if c.error else "")
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval layer benchmark")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Include live AgentLayer repo cases (or set RETRIEVAL_BENCH_LIVE=1)",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default="",
        help="Override workspace path (default: fixture mini or repo root when --live)",
    )
    parser.add_argument("--json-out", type=str, default="", help="Write full report JSON here")
    args = parser.parse_args()

    live = args.live or os.environ.get("RETRIEVAL_BENCH_LIVE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if args.workspace:
        workspace = args.workspace
    elif live:
        workspace = str(repo_root())
    else:
        workspace = str(fixture_workspace_path())

    cases = cases_for_run(live=live)
    if not cases:
        print("No benchmark cases selected.", file=sys.stderr)
        return 1

    print(f"Retrieval benchmark ({len(cases)} cases, live={live})")
    reports = compare_strategies(cases, workspace_path=workspace)
    _print_report("unified (retrieve_context)", reports["unified"])
    _print_report("separate (grep + semantic + …)", reports["separate"])

    u, s = reports["unified"], reports["separate"]
    saved_calls = s.mean_tool_calls - u.mean_tool_calls
    print("\n-- comparison --")
    print(f"  tool calls saved per query (unified vs separate): {saved_calls:.2f}")
    if u.hit_rate != s.hit_rate:
        print(f"  hit rate delta (unified - separate): {(u.hit_rate - s.hit_rate):+.2%}")

    if args.json_out:
        out = {k: v.to_dict() for k, v in reports.items()}
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json_out}")

    return 0 if u.hit_rate >= 0.8 else 2


if __name__ == "__main__":
    raise SystemExit(main())
