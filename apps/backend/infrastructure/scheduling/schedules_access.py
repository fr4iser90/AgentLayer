"""Load schedules feature access from DB (admin-only default + per-user grant)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.domain.scheduling.access import (
    evaluate_schedules_access,
    schedules_feature_denied_message,
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


def user_may_use_schedules(
    *,
    user_id: uuid.UUID | None = None,
    user: Any | None = None,
) -> bool:
    """The schedules feature for one account: site admin, or the named grant.

    Takes an identity, not a role string. A role handed in by a caller is the
    legacy ``users.role`` (``infrastructure/identity/auth.py`` builds it from that
    column), so accepting one here meant an account whose ``site_role`` says
    ``site_user`` still got the feature — and there was nothing an admin could flip
    to take it back.

    No resolvable id and no readable ``site_role`` both deny: this gate guards
    creating schedules that run on the instance, so an unreadable identity confers
    nothing (ADR 0011 §1).
    """
    uid = _resolve_uid(user_id, user)
    if uid is None:
        return False

    try:
        from apps.backend.infrastructure.db import db

        site = db.user_site_role(uid)
        allowed = False
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(  # tenant-scope: guarded by user_id pk — the row read is the caller's own account
                    "SELECT COALESCE(schedules_allowed, false) FROM users WHERE id = %s",
                    (uid,),
                )
                row = cur.fetchone()
        if row is not None:
            allowed = bool(row[0])
        return evaluate_schedules_access(site_role=site, schedules_allowed=allowed)
    except Exception as e:
        logger.warning("failed to check schedules_allowed: %s", e)
        return False


def schedule_feature_permission_error(
    *,
    user_id: uuid.UUID | None = None,
    user: Any | None = None,
) -> str | None:
    if user_may_use_schedules(user_id=user_id, user=user):
        return None
    return schedules_feature_denied_message()


# Re-export for callers that previously imported the pure helper name.
__all__ = [
    "schedule_feature_permission_error",
    "user_may_use_schedules",
]
