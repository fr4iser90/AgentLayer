"""Agent runtime entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.agent_runtime.value_objects import AgentId, AgentRunId


@dataclass(slots=True)
class AgentRun:
    id: AgentRunId
    agent_id: AgentId
    status: str
    user_id: str
    transcript: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in {"queued", "running", "waiting", "succeeded", "failed", "cancelled"}:
            raise ValueError("invalid agent run status")
        if not self.user_id.strip():
            raise ValueError("agent run user_id must not be blank")

    def append_transcript(self, line: str) -> None:
        value = line.strip()
        if value:
            self.transcript.append(value)


@dataclass(frozen=True, slots=True)
class AgentTurn:
    run_id: AgentRunId
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant", "tool", "system"}:
            raise ValueError("invalid agent turn role")
        if not self.content.strip():
            raise ValueError("agent turn content must not be blank")
