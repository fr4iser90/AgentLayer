"""Infrastructure adapter for user persona prompt injection."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain import user_persona as domain
from apps.backend.infrastructure.db import db


class _UserPersonaDeps:
    @staticmethod
    def user_agent_profile_get(user_id: uuid.UUID) -> dict[str, Any] | None:
        return db.user_agent_profile_get(user_id)

    @staticmethod
    def user_persona_get(user_id: uuid.UUID) -> dict[str, Any] | None:
        return db.user_persona_get(user_id)


domain.register_user_persona_dependencies(_UserPersonaDeps())

apply_user_persona_system = domain.apply_user_persona_system
format_agent_profile_summary = domain.format_agent_profile_summary
