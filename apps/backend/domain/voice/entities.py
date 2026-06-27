"""Voice entities."""
from __future__ import annotations

from dataclasses import dataclass

from apps.backend.domain.voice.value_objects import VoiceId, VoiceProvider


@dataclass(slots=True)
class VoiceProfile:
    id: VoiceId
    provider: VoiceProvider
    display_name: str
    language: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise ValueError("voice display name must not be blank")
        if self.language is not None and len(self.language.strip()) > 16:
            raise ValueError("voice language tag is too long")


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    voice_id: VoiceId
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("speech text must not be blank")
