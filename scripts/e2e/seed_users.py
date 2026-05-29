#!/usr/bin/env python3
"""Seed E2E User B via admin API (idempotent). Loads .env + .env.e2e."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.e2e.helpers import E2EClient, admin_credentials, ensure_user_b, load_e2e_env, require_server


def main() -> int:
    load_e2e_env()
    admin: E2EClient | None = None
    user_b: E2EClient | None = None
    try:
        require_server()
        email, password = admin_credentials()
        admin = E2EClient.login(email, password)
        user_b = ensure_user_b(admin)
    except Exception as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if admin is not None:
            admin.close()
        if user_b is not None:
            user_b.close()

    print(f"E2E User B ready: {user_b.email} id={user_b.user_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
