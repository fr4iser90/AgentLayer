"""Model routing value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "ModelId":
        value = raw.strip()
        if not value:
            raise ValueError("model id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class RoutingProfile:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "RoutingProfile":
        value = raw.strip().lower()
        if not value:
            raise ValueError("routing profile must not be blank")
        return cls(value)
