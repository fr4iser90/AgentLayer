#!/usr/bin/env python3
"""
Remove leftover E2E / IDOR test resources from a running Agent Layer instance.

Deletes conversations, dashboards, and workspaces created by ``tests/e2e/test_auth_idor_matrix.py``
(legacy titles like ``IDOR conv …`` and new ``[E2E IDOR] …`` prefix).

Does not delete tasks (no DELETE API yet) or touch persona/memory probes.

Examples:
  PYTHONPATH=. python3 scripts/e2e_cleanup.py
  PYTHONPATH=. python3 scripts/e2e_cleanup.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.e2e.support.helpers import E2EClient, admin_credentials, load_e2e_env  # noqa: E402
from tests.e2e.support.cleanup import cleanup_idor_orphans  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up E2E / IDOR sandbox resources")
    parser.add_argument("--dry-run", action="store_true", help="Count matches without deleting")
    args = parser.parse_args()

    load_e2e_env()
    try:
        email, password = admin_credentials()
        client = E2EClient.login(email, password)
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    print(f"E2E cleanup dry_run={args.dry_run}")
    try:
        stats = cleanup_idor_orphans(client, dry_run=args.dry_run)
    finally:
        client.close()

    print(
        f"Done: conversations={stats.conversations} "
        f"dashboards={stats.dashboards} workspaces={stats.workspaces}"
    )
    if stats.conversations == 0 and stats.dashboards == 0 and stats.workspaces == 0:
        print("Nothing to clean (or server unreachable / wrong account).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
