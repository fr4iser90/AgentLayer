#!/usr/bin/env python3
"""
Run agent LLM benchmarks (live models) and write JSON + summary.csv.

Examples:
  python scripts/run_agent_benchmark.py
  python scripts/run_agent_benchmark.py --manifest benchmarks/manifests/workspace.yaml
  python scripts/run_agent_benchmark.py --manifest benchmarks/manifests/social.yaml --profile ollama-small
  python scripts/run_agent_benchmark.py --manifest benchmarks/manifests/full.yaml
  python scripts/run_agent_benchmark.py --only W1_git_readme_no_index
  python scripts/run_agent_benchmark.py --manifest benchmarks/manifests/full.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.benchmarks.agent.harness import (  # noqa: E402
    print_summary_table,
    repo_root,
    run_benchmark,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent LLM provider/model benchmark")
    parser.add_argument(
        "--manifest",
        type=str,
        default="",
        help="Manifest YAML (default: benchmarks/manifest.yaml → smoke suite)",
    )
    parser.add_argument("--tier", type=int, default=None, help="Max tier (default: manifest tier_max)")
    parser.add_argument("--profile", type=str, default="", help="Run only this profile label")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated scenario ids (overrides manifest scenario list)",
    )
    parser.add_argument(
        "--fixtures",
        type=str,
        default="",
        help="Extra fixture ids to apply (comma-separated)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Output directory (default: benchmarks/results/)",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest) if args.manifest else repo_root() / "benchmarks" / "manifest.yaml"
    if not manifest_path.is_file():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    scenario_filter = [s.strip() for s in args.only.split(",") if s.strip()] or None
    extra_fixtures = [f.strip() for f in args.fixtures.split(",") if f.strip()] or None

    try:
        report = run_benchmark(
            manifest_path=manifest_path,
            tier=args.tier,
            profile_filter=args.profile.strip() or None,
            scenario_filter=scenario_filter,
            extra_fixtures=extra_fixtures,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_summary_table(report)

    out_root = Path(args.json_out) if args.json_out else repo_root() / "benchmarks" / "results"
    run_dir = write_report(report, out_root)
    print(f"\nWrote results to {run_dir}")
    print(f"Cleanup: python scripts/bench_cleanup.py --prefix {report.resource_prefix}")

    failures = [r for r in report.results if not r.skipped and not r.passed]
    if failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
