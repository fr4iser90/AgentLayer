"""Load dashboard feature access from DB (global flag + per-user grant + quota).

Mirrors ``infrastructure/scheduling/schedules_access.py``: the pure rule lives in
``domain/dashboards/access``; this module resolves the global operator flag, the per-user
``dashboards_allowed`` grant and the ``dashboard_quota`` cap, then applies the pure rule.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.dashboards.access import (
    dashboards_feature_denied_message,
    dashboards_quota_reached_message,
    evaluate_dashboards_access,
)

logger = logging.getLogger(__name__)


def _resolve_uid(
    user_id: uuid.UUID | None,
    user: Any | None,
) -> uuid.UUID | None:
    if isinstance(user_id, uuid.UUID):
        return user_id
    if user_id is not None:
        try:
            return uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            pass
    if user is None:
        return None
    raw = getattr(user, "id", None)
    if isinstance(raw, uuid.UUID):
        return raw
    if raw is not None:
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError):
            return None
    return None


def global_dashboards_enabled() -> bool:
    """Operator-wide gate (``operator_settings.dashboards_allowed``); default true (fail-open)."""
    try:
        from apps.backend.infrastructure.settings.operator_settings import public_dict

        return bool(public_dict().get("dashboards_allowed", True))
    except Exception:
        return True


def _load_user_dashboards_allowed(uid: uuid.UUID) -> bool:
    """Fail open (``True``) so the column default preserves auto-create behavior."""
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                # tenant-scope: guarded by uid — the row is keyed to one user's
                # own id, so the read cannot cross a tenant boundary.
                cur.execute(
                    "SELECT COALESCE(dashboards_allowed, true) FROM users WHERE id = %s",
                    (uid,),
                )
                row = cur.fetchone()
        return bool(row and row[0]) if row else True
    except Exception:
        return True


def dashboards_quota_for(user_id: uuid.UUID | None) -> int:
    """Per-user dashboard quota (``users.dashboard_quota``); default 1, floored at 1."""
    uid = _resolve_uid(user_id, None)
    if uid is None:
        return 1
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                # tenant-scope: guarded by uid — one user's own quota row.
                cur.execute(
                    "SELECT COALESCE(dashboard_quota, 1) FROM users WHERE id = %s",
                    (uid,),
                )
                row = cur.fetchone()
        n = int(row[0]) if row and row[0] is not None else 1
    except Exception:
        # Logged, not silent. This reader previously named the column
        # `dashboards_quota`, which does not exist, so every call raised
        # UndefinedColumn and fell through to 1 — leaving the real
        # `dashboard_quota` column (written by the admin API) unread and
        # every user capped at one dashboard with nothing to show for it.
        logger.warning("dashboards_quota_for: could not read quota for %s", uid, exc_info=True)
        n = 1
    return max(1, n)


def current_dashboards_count(user_id: uuid.UUID, tenant_id: int) -> int:
    """Count dashboards owned by a user in a tenant (dashboards quota gate)."""
    uid = _resolve_uid(user_id, None)
    if uid is None:
        return 0
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_dashboards WHERE owner_user_id = %s AND tenant_id = %s",
                    (uid, tenant_id),
                )
                row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def delete_user_dashboards(user_id: uuid.UUID) -> int:
    """Delete every dashboard owned by a user (e.g. after a per-user revoke). Returns row count."""
    uid = _resolve_uid(user_id, None)
    if uid is None:
        return 0
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                # tenant-scope: guarded by owner_user_id — deletes only the
                # caller's own dashboards, never another owner's.
                cur.execute("DELETE FROM user_dashboards WHERE owner_user_id = %s", (uid,))
                n = cur.rowcount or 0
    except Exception:
        logger.warning("delete_user_dashboards failed (user_id=%s)", uid, exc_info=True)
        return 0
    return n


def user_may_use_dashboards(
    *,
    user_id: uuid.UUID | None = None,
    user: Any | None = None,
) -> bool:
    """Global operator gate + admin/site_admin always + per-user grant.

    Mirrors ``infrastructure/scheduling/schedules_access``: the global operator flag gates
    everyone, then the pure rule in ``domain/dashboards/access`` decides using the
    authoritative role/site_role resolved from the DB (falling back to ``user.role``) and the
    per-user ``dashboards_allowed`` grant.
    """
    if not global_dashboards_enabled():
        return False
    role = str(getattr(user, "role", None) if user is not None else "").strip().lower()
    uid = _resolve_uid(user_id, user)
    if uid is None:
        return evaluate_dashboards_access(user_role=role, dashboards_allowed=False)
    try:
        from apps.backend.infrastructure.db import db

        db_role = db.user_role(uid)
        site = db.user_site_role(uid)
        return evaluate_dashboards_access(
            user_role=db_role or role,
            site_role=site,
            dashboards_allowed=_load_user_dashboards_allowed(uid),
        )
    except Exception:
        logger.warning("failed to resolve dashboard access (user_id=%s)", uid, exc_info=True)
        return evaluate_dashboards_access(user_role=role, dashboards_allowed=False)


def dashboards_feature_permission_error(
    user: Any | None,
    *,
    current_count: int = 0,
    quota: int = 1,
) -> str | None:
    """Full create gate: access (global + per-user + admin) and the quota cap.

    Returns ``None`` when the user may create another dashboard, else the reason.
    """
    if user_may_use_dashboards(user=user):
        return None if current_count < quota else dashboards_quota_reached_message()
    return dashboards_feature_denied_message()


# Re-export for callers that previously imported the pure helper name.
__all__ = [
    "dashboards_feature_permission_error",
    "dashboards_feature_denied_message",
    "dashboards_quota_reached_message",
    "dashboards_quota_for",
    "current_dashboards_count",
    "delete_user_dashboards",
    "global_dashboards_enabled",
    "user_may_use_dashboards",
]
