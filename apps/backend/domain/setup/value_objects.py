"""Setup value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetupStepKey:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "SetupStepKey":
        value = raw.strip()
        if not value:
            raise ValueError("setup step key must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class SetupProfileName:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "SetupProfileName":
        value = raw.strip()
        if not value or len(value) > 120:
            raise ValueError("setup profile name must be 1..120 characters")
        return cls(value)
