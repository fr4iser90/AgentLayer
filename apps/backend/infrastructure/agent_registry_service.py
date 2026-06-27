"""Infrastructure adapter for agent registry policy overlays."""

from __future__ import annotations

from typing import Any

from apps.backend.domain import agent_registry as domain
from apps.backend.infrastructure.agent_config_effective import merge_agent_definition
from apps.backend.infrastructure.tool_operator_policy_db import policies_map


class _AgentRegistryDeps:
    @staticmethod
    def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
        return policies_map()

    @staticmethod
    def merge_agent_definition(agent: dict[str, Any]) -> dict[str, Any]:
        return merge_agent_definition(agent)


domain.register_agent_registry_dependencies(_AgentRegistryDeps())

AgentRegistry = domain.AgentRegistry
effective_tool_names_for_caller = domain.effective_tool_names_for_caller
get_agent_registry = domain.get_agent_registry
resolve_agent_tool_names = domain.resolve_agent_tool_names
