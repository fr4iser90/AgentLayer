"""Voice read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetVoiceProfileQuery:
    voice_id: str


@dataclass(frozen=True, slots=True)
class ListVoiceProfilesQuery:
    provider: str | None = None
