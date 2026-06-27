"""Agent runtime value objects."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentRunId:
    value: uuid.UUID

    @classmethod
    def parse(cls, raw: str | uuid.UUID) -> "AgentRunId":
        return cls(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))


@dataclass(frozen=True, slots=True)
class AgentId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "AgentId":
        value = raw.strip()
        if not value:
            raise ValueError("agent id must not be blank")
        return cls(value)
