"""Infrastructure adapter for plugin registry runtime concerns."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.plugin_system import registry as domain
from apps.backend.infrastructure.platform import config
from apps.backend.infrastructure.agent_runtime import agent_config_effective
from apps.backend.infrastructure.agent_runtime.agent_config_router_overlay import overlay_phrases_for_domain
from apps.backend.infrastructure.db import db


class _PluginRegistryDeps(domain.PluginRegistryDependencies):
    def tool_scan_directories(self):
        return config.tool_scan_directories()

    def tools_allowed_sha256(self):
        return config.tools_allowed_sha256()

    def tools_extra_dir(self) -> str:
        return config.TOOLS_EXTRA_DIR

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
