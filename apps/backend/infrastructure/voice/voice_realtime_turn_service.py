"""Infrastructure adapter for one voice realtime turn."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.application.agent_runtime.use_cases.chat_completion import chat_completion
from apps.backend.domain.voice import realtime_turn as domain
from apps.backend.infrastructure.db import db


class _VoiceRealtimeTurnDeps:
    @staticmethod
    def user_role(user_id: uuid.UUID) -> str:
        return db.user_role(user_id)

    @staticmethod
    async def chat_completion(body: dict[str, Any], *, bearer_user_role: str | None = None) -> Any:
        return await chat_completion(body, bearer_user_role=bearer_user_role)


domain.register_voice_realtime_turn_dependencies(_VoiceRealtimeTurnDeps())

run_voice_realtime_turn = domain.run_voice_realtime_turn
