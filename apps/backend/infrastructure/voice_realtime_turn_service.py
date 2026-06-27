"""Infrastructure adapter for one voice realtime turn."""

from __future__ import annotations

import uuid

from apps.backend.domain.voice import realtime_turn as domain
from apps.backend.infrastructure.db import db


class _VoiceRealtimeTurnDeps:
    @staticmethod
    def user_role(user_id: uuid.UUID) -> str:
        return db.user_role(user_id)


domain.register_voice_realtime_turn_dependencies(_VoiceRealtimeTurnDeps())

run_voice_realtime_turn = domain.run_voice_realtime_turn
