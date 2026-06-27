"""Agent runtime DTOs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentRunDto:
    run_id: uuid.UUID
    agent_id: str
    status: str
    user_id: str
    transcript: list[str] = field(default_factory=list)
