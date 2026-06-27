"""Delegation entities."""
from __future__ import annotations

from dataclasses import dataclass

from apps.backend.domain.delegation.value_objects import DelegateAgentId, DelegationId


@dataclass(slots=True)
class DelegationTask:
    id: DelegationId
    delegate_agent_id: DelegateAgentId
    instruction: str
    status: str = "requested"

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("delegation instruction must not be blank")
        if self.status not in {"requested", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("invalid delegation status")

    def mark_running(self) -> None:
        self.status = "running"
