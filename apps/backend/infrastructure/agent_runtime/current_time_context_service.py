"""Infrastructure adapter for per-user current-time context."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.agent_runtime import time_context as domain
from apps.backend.infrastructure.db import db


class _CurrentTimeContextDeps:
    @staticmethod
    def user_timezone_persist(tenant_id: int, user_id: uuid.UUID, timezone_name: str) -> None:
        db.user_timezone_persist(tenant_id, user_id, timezone_name)

    @staticmethod
    def user_agent_profile_get(user_id: uuid.UUID) -> dict[str, Any] | None:
        return db.user_agent_profile_get(user_id)


domain.register_current_time_context_dependencies(_CurrentTimeContextDeps())

USER_TIMEZONE_HEADER = domain.USER_TIMEZONE_HEADER
apply_current_time_context = domain.apply_current_time_context
build_current_time_context_snippet = domain.build_current_time_context_snippet
normalize_timezone_name = domain.normalize_timezone_name
resolve_user_timezone = domain.resolve_user_timezone
