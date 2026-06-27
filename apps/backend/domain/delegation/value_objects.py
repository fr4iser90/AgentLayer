"""Delegation value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DelegationId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "DelegationId":
        value = raw.strip()
        if not value:
            raise ValueError("delegation id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class DelegateAgentId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "DelegateAgentId":
        value = raw.strip()
        if not value:
            raise ValueError("delegate agent id must not be blank")
        return cls(value)
