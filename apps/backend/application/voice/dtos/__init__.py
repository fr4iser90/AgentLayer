"""Voice DTOs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceProfileDto:
    voice_id: str
    provider: str
    display_name: str
    language: str | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class SpeechRequestDto:
    voice_id: str
    text: str
