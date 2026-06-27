"""Studio value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StudioJobId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "StudioJobId":
        value = raw.strip()
        if not value:
            raise ValueError("studio job id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class StudioJobKind:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "StudioJobKind":
        value = raw.strip().lower()
        if not value:
            raise ValueError("studio job kind must not be blank")
        return cls(value)
