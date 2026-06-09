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
from typing import Any

import httpx

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.benchmarks.agent.harness import bench_credentials, load_bench_env  # noqa: E402
from tests.e2e.support.helpers import E2EClient  # noqa: E402


def _matches_prefix(name: str, prefix: str) -> bool:
    return bool(prefix) and (name or "").startswith(prefix)


def _delete_resource(
    client: E2EClient,
    method: str,
    path: str,
    *,
    dry_run: bool,
    label: str,
) -> bool:
    if dry_run:
        print(f"  [dry-run] would DELETE {label}")
        return True
    resp = client.http.request(method, path)
    if resp.status_code in (200, 204, 404):
        print(f"  deleted {label} ({resp.status_code})")
        return True
    print(f"  failed {label}: HTTP {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    return False


def cleanup_prefix(
    client: E2EClient,
    *,
    prefix: str,
    dry_run: bool,
    include_conversations: bool,
) -> dict[str, int]:
    stats = {"workspaces": 0, "dashboards": 0, "conversations": 0}

    ws_data = client.get_json("/v1/workspaces")
    for ws in ws_data.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        name = str(ws.get("name") or "")
        wid = str(ws.get("id") or "")
        if not _matches_prefix(name, prefix):
            continue
        if _delete_resource(client, "DELETE", f"/v1/workspaces/{wid}", dry_run=dry_run, label=f"workspace {name!r}"):
            stats["workspaces"] += 1

    dash_data = client.get_json("/v1/dashboards")
    for dash in dash_data.get("dashboards") or []:
        if not isinstance(dash, dict):
            continue
        title = str(dash.get("title") or dash.get("name") or "")
        did = str(dash.get("id") or "")
        if not _matches_prefix(title, prefix):
            continue
        if _delete_resource(client, "DELETE", f"/v1/dashboards/{did}", dry_run=dry_run, label=f"dashboard {title!r}"):
            stats["dashboards"] += 1

    if include_conversations:
        conv_data = client.get_json("/v1/user/conversations")
        rows: list[Any] = conv_data.get("conversations") or conv_data.get("items") or []
        for conv in rows:
            if not isinstance(conv, dict):
                continue
            title = str(conv.get("title") or "")
            cid = str(conv.get("id") or "")
            if not _matches_prefix(title, prefix):
                continue
            if _delete_resource(
                client,
                "DELETE",
                f"/v1/user/conversations/{cid}",
                dry_run=dry_run,
                label=f"conversation {title!r}",
            ):
                stats["conversations"] += 1

    return stats


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
    try:
        stats = cleanup_prefix(
            client,
            prefix=prefix,
            dry_run=args.dry_run,
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
