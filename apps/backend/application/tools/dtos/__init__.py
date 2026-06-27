"""Tool system DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ToolDefinitionDto:
    name: str
    namespace: str
    description: str
    input_schema: dict[str, object] = field(default_factory=dict)
    enabled: bool = True
