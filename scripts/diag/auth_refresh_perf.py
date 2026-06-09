#!/usr/bin/env python3
"""
E2E probe: POST /auth/refresh latency vs refresh_tokens row count.

Proves (or disproves) the login-spinner bug in validate_refresh_token O(n) bcrypt.

  python3 scripts/diag/auth_refresh_perf.py
  python3 scripts/diag/auth_refresh_perf.py --json

Exit 1 when the scaling bug is confirmed (expected until auth.py is fixed).
Exit 0 when scaling is flat (bug fixed or not reproduced).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.e2e.support.auth_refresh_scaling import (  # noqa: E402
    format_failure,
    is_bug_confirmed,
    run_scaling_report,
)
from tests.e2e.support.helpers import load_e2e_env, require_server  # noqa: E402


def print_human(report) -> None:
    print("\n=== Auth refresh scaling E2E ===\n")
    print(format_failure(report))
    if is_bug_confirmed(report):
        print("\nRESULT: BUG CONFIRMED — validate_refresh_token still slow (see report above)")
    else:
        print("\nRESULT: OK — refresh stays fast (sha256 indexed lookup)")


def main() -> int:
    load_e2e_env()
    p = argparse.ArgumentParser(description="Auth refresh token scaling E2E probe")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--rounds",
        default="1,21,41",
        help="Comma-separated login counts per sample (default 1,21,41)",
    )
    args = p.parse_args()

    try:
        require_server()
    except RuntimeError as exc:
        print(f"[auth-refresh-perf] {exc}", file=sys.stderr)
        return 2

    rounds = [int(x.strip()) for x in args.rounds.split(",") if x.strip()]
    report = run_scaling_report(login_rounds=rounds)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human(report)

    return 1 if is_bug_confirmed(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
