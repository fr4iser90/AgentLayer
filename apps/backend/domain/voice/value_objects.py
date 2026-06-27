"""Voice value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "VoiceId":
        value = raw.strip()
        if not value:
            raise ValueError("voice id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class VoiceProvider:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "VoiceProvider":
        value = raw.strip().lower()
        if not value:
            raise ValueError("voice provider must not be blank")
        return cls(value)
