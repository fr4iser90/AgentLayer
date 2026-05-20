"""
First admin: only via AGENT_INITIAL_ADMIN_EMAIL + AGENT_INITIAL_ADMIN_PASSWORD before first start.
"""
from __future__ import annotations

import logging

from apps.backend.core.config import AGENT_INITIAL_ADMIN_EMAIL, AGENT_INITIAL_ADMIN_PASSWORD
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.auth import insert_user_with_cursor
from apps.backend.dashboard.db import ensure_default_dashboard_for_new_user

logger = logging.getLogger(__name__)


def is_first_start() -> bool:
    """True when no admin user exists."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_count = cur.fetchone()[0]
            return admin_count == 0


def try_create_initial_admin_from_env() -> bool:
    """
    If AGENT_INITIAL_ADMIN_EMAIL and AGENT_INITIAL_ADMIN_PASSWORD are both set, create the first
    admin once.
    """
    email = AGENT_INITIAL_ADMIN_EMAIL
    password = AGENT_INITIAL_ADMIN_PASSWORD
    if not email or not password:
        return False
    if len(password) < 8:
        logger.warning(
            "AGENT_INITIAL_ADMIN_PASSWORD must be at least 8 characters; env bootstrap skipped"
        )
        return False

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(872814001)")
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if cur.fetchone()[0] > 0:
                conn.rollback()
                return False
            new_admin = insert_user_with_cursor(cur, email, password, role="admin")
            cur.execute("DELETE FROM admin_claim_otp")
        conn.commit()

    logger.info(
        "First admin created from AGENT_INITIAL_ADMIN_EMAIL. "
        "Remove AGENT_INITIAL_ADMIN_* from the environment and change the password after login."
    )
    # tenant_id=1 matches insert_user_with_cursor default for first admin
    ensure_default_dashboard_for_new_user(new_admin.id, 1)
    return True


def setup_admin_claim_if_needed() -> None:
    """Delegate to instance_setup (env bootstrap or /app/setup)."""
    from apps.backend.domain.instance_setup import setup_admin_claim_if_needed as _run

    _run()
