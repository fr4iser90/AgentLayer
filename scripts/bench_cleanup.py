#!/usr/bin/env python3
"""
Delete benchmark sandbox resources (workspaces, dashboards, conversations) by prefix.

Does NOT delete benchmarks/results/ JSON unless --include-results is set.

Examples:
  python scripts/bench_cleanup.py --prefix bench- --dry-run
  python scripts/bench_cleanup.py --prefix bench-20260608T120000-
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.benchmarks.agent.bench_cleanup import (  # noqa: E402
    cleanup_prefix,
    list_user_workspaces,
    matches_bench_prefix,
)
from tests.benchmarks.agent.harness import bench_credentials, load_bench_env  # noqa: E402
from tests.e2e.support.helpers import E2EClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up benchmark sandbox resources by name prefix")
    parser.add_argument("--prefix", type=str, default="bench-", help="Name/title prefix to match")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deleting")
    parser.add_argument(
        "--include-conversations",
        action="store_true",
        help="Also delete conversations whose title starts with prefix",
    )
    parser.add_argument(
        "--include-results",
        action="store_true",
        help="Also remove benchmarks/results/ directories matching prefix (local filesystem)",
    )
    args = parser.parse_args()

    prefix = (args.prefix or "bench-").strip()
    if not prefix:
        print("--prefix must be non-empty", file=sys.stderr)
        return 1

    load_bench_env()
    try:
        email, password = bench_credentials()
        client = E2EClient.login(email, password)
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    print(f"Benchmark cleanup prefix={prefix!r} dry_run={args.dry_run}")
    stats = {"workspaces": 0, "dashboards": 0, "conversations": 0}
    try:
        if args.dry_run:
            for ws in list_user_workspaces(client):
                name = str(ws.get("name") or "")
                if matches_bench_prefix(name, prefix):
                    print(f"  [dry-run] would DELETE workspace {name!r}")
                    stats["workspaces"] += 1
            dash_data = client.get_json("/v1/dashboards")
            for dash in dash_data.get("dashboards") or []:
                if not isinstance(dash, dict):
                    continue
                title = str(dash.get("title") or dash.get("name") or "")
                if matches_bench_prefix(title, prefix):
                    print(f"  [dry-run] would DELETE dashboard {title!r}")
                    stats["dashboards"] += 1
        else:
            stats = cleanup_prefix(
                client,
                prefix=prefix,
                dry_run=False,
                include_conversations=args.include_conversations,
            )
    finally:
        client.close()

    print(
        f"Done: workspaces={stats['workspaces']} "
        f"dashboards={stats['dashboards']} conversations={stats['conversations']}"
    )

    if args.include_results and not args.dry_run:
        results_root = _REPO / "benchmarks" / "results"
        removed = 0
        if results_root.is_dir():
            for child in results_root.iterdir():
                if child.is_dir() and child.name.startswith(prefix.rstrip("-")):
                    import shutil

                    shutil.rmtree(child)
                    removed += 1
                    print(f"  removed results dir {child}")
        print(f"Removed {removed} result directories")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
