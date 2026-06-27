"""Tool system use cases."""
from __future__ import annotations

from apps.backend.application.tools.commands import SaveToolDefinitionCommand
from apps.backend.application.tools.dtos import ToolDefinitionDto
from apps.backend.application.tools.ports import ToolDefinitionRepository
from apps.backend.application.tools.queries import GetToolDefinitionQuery, ListToolDefinitionsQuery
from apps.backend.domain.tools.entities import ToolDefinition
from apps.backend.domain.tools.schemas import validate_tool_input_schema
from apps.backend.domain.tools.value_objects import ToolName, ToolNamespace


def _to_dto(definition: ToolDefinition) -> ToolDefinitionDto:
    return ToolDefinitionDto(
        name=definition.name.value,
        namespace=definition.namespace.value,
        description=definition.description,
        input_schema=dict(definition.input_schema),
        enabled=definition.enabled,
    )


def get_tool_definition(repo: ToolDefinitionRepository, query: GetToolDefinitionQuery) -> ToolDefinitionDto | None:
    definition = repo.get(ToolName.parse(query.name))
    return _to_dto(definition) if definition else None


def list_tool_definitions(repo: ToolDefinitionRepository, query: ListToolDefinitionsQuery) -> list[ToolDefinitionDto]:
    namespace = ToolNamespace.parse(query.namespace) if query.namespace else None
    return [_to_dto(item) for item in repo.list_by_namespace(namespace)]


def save_tool_definition(repo: ToolDefinitionRepository, command: SaveToolDefinitionCommand) -> ToolDefinitionDto:
    definition = ToolDefinition(
        name=ToolName.parse(command.name),
        namespace=ToolNamespace.parse(command.namespace),
        description=command.description,
        input_schema=validate_tool_input_schema(command.input_schema),
        enabled=command.enabled,
    )
    return _to_dto(repo.save(definition))
