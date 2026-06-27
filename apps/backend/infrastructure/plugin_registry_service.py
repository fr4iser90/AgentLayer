"""Infrastructure adapter for plugin registry runtime concerns."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.plugin_system import registry as domain
from apps.backend.infrastructure import agent_config_effective
from apps.backend.infrastructure.agent_config_router_overlay import overlay_phrases_for_domain
from apps.backend.infrastructure.db import db


class _PluginRegistryDeps(domain.PluginRegistryDependencies):
    def effective_domain_order(self) -> list[str]:
        return agent_config_effective.effective_domain_order()

    def overlay_phrases_for_domain(self, domain_name: str) -> list[str]:
        return list(overlay_phrases_for_domain(domain_name))

    def log_tool_invocation(
        self,
        name: str,
        arguments: dict[str, Any],
        result: str,
        ok: bool,
        *,
        agent_run_id: Any = None,
    ) -> None:
        db.log_tool_invocation(name, arguments, result, ok, agent_run_id=agent_run_id)


domain.register_plugin_registry_dependencies(_PluginRegistryDeps())

ToolRegistry = domain.ToolRegistry
get_registry = domain.get_registry
reload_registry = domain.reload_registry
