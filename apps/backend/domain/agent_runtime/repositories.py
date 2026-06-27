"""Repository ports for agent runtime."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.agent_runtime.entities import AgentRun, AgentTurn
from apps.backend.domain.agent_runtime.value_objects import AgentRunId


class AgentRunRepository(Protocol):
    def get(self, run_id: AgentRunId) -> AgentRun | None: ...

    def save(self, run: AgentRun) -> AgentRun: ...

    def append_turn(self, turn: AgentTurn) -> None: ...
