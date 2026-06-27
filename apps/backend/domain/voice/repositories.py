"""Repository ports for voice profiles."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.voice.entities import VoiceProfile
from apps.backend.domain.voice.value_objects import VoiceId, VoiceProvider


class VoiceProfileRepository(Protocol):
    def get(self, voice_id: VoiceId) -> VoiceProfile | None: ...

    def list_by_provider(self, provider: VoiceProvider | None = None) -> list[VoiceProfile]: ...

    def save(self, profile: VoiceProfile) -> VoiceProfile: ...
