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
    user_role: str | None = None,
    user: Any | None = None,
) -> bool:
    role = str(user_role or getattr(user, "role", None) or "").strip().lower()
    if role == "admin":
        return True

    uid = _resolve_uid(user_id, user)
    if uid is None:
        return evaluate_schedules_access(user_role=role, schedules_allowed=False)

    try:
        from apps.backend.infrastructure.db import db

        db_role = db.user_role(uid)
        site = db.user_site_role(uid)
        allowed = False
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(schedules_allowed, false) FROM users WHERE id = %s",
                    (uid,),
                )
                row = cur.fetchone()
        if row is not None:
            allowed = bool(row[0])
        return evaluate_schedules_access(
            user_role=db_role or role,
            site_role=site,
            schedules_allowed=allowed,
        )
    except Exception as e:
        logger.warning("failed to check schedules_allowed: %s", e)
        return evaluate_schedules_access(user_role=role, schedules_allowed=False)


def schedule_feature_permission_error(
    *,
    user_id: uuid.UUID | None = None,
    user_role: str | None = None,
    user: Any | None = None,
) -> str | None:
    if user_may_use_schedules(user_id=user_id, user_role=user_role, user=user):
        return None
    return schedules_feature_denied_message()


# Re-export for callers that previously imported the pure helper name.
__all__ = [
    "schedule_feature_permission_error",
    "user_may_use_schedules",
]
