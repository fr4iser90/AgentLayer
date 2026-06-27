"""Repository ports for tool catalog data."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.tools.entities import ToolDefinition
from apps.backend.domain.tools.value_objects import ToolName, ToolNamespace


class ToolDefinitionRepository(Protocol):
    def get(self, name: ToolName) -> ToolDefinition | None: ...

    def list_by_namespace(self, namespace: ToolNamespace | None = None) -> list[ToolDefinition]: ...

    def save(self, definition: ToolDefinition) -> ToolDefinition: ...
