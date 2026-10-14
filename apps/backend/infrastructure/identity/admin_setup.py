"""
First-start detection: no elevated account yet → setup wizard at /app/setup.
"""

from __future__ import annotations

from apps.backend.domain.identity.roles import ELEVATED_SQL
from apps.backend.infrastructure.db import db


def is_first_start() -> bool:
    """True when no elevated account exists yet (the domain rule, not the legacy column)."""
    with db.pool().connection() as conn:  # tenant-scope: site-wide — nothing exists yet
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM users WHERE {ELEVATED_SQL}")
            admin_count = cur.fetchone()[0]
            return admin_count == 0
