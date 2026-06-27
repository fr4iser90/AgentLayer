"""Tool entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.tools.value_objects import ToolName, ToolNamespace


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: ToolName
    namespace: ToolNamespace
    description: str
    input_schema: dict[str, object] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("tool description must not be blank")


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    tool_name: ToolName
    arguments: dict[str, object]
    actor_user_id: str | None = None
