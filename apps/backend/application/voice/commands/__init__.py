"""Voice write commands."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SaveVoiceProfileCommand:
    voice_id: str
    provider: str
    display_name: str
    language: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PrepareSpeechCommand:
    voice_id: str
    text: str
