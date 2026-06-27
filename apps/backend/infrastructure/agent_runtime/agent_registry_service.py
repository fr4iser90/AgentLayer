"""Infrastructure adapter for agent registry policy overlays."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from apps.backend.domain.agent_runtime import access
from apps.backend.domain.agent_runtime import registry as domain
from apps.backend.domain.agent_runtime import subagent_catalog
from apps.backend.infrastructure.platform import config
from apps.backend.infrastructure.agent_runtime import agent_config_effective
from apps.backend.infrastructure.agent_runtime import agent_access_policy_store
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.agent_runtime.agent_config_effective import merge_agent_definition
from apps.backend.infrastructure.tools.tool_operator_policy_db import policies_map


class _AgentRegistryDeps:
    @staticmethod
    def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
        return policies_map()

    @staticmethod
    def merge_agent_definition(agent: dict[str, Any]) -> dict[str, Any]:
        return merge_agent_definition(agent)

    @staticmethod
    def agent_plugin_dirs() -> list[Path]:
        dirs = [config.PLUGINS_DIR / "agents"]
        raw = os.environ.get("AGENT_PLUGINS_DIR", "").strip()
        if raw:
            for item in raw.split(","):
                path = Path(item.strip())
                if path.is_dir() and path not in dirs:
                    dirs.append(path)
        return dirs

    @staticmethod
    def plugins_root() -> Path | None:
        return config.PLUGINS_DIR.parent


domain.register_agent_registry_dependencies(_AgentRegistryDeps())


class _SubagentCatalogDeps:
    @staticmethod
    def user_role(user_id) -> str:
        return db.user_role(user_id)

    @staticmethod
    def effective_string_list(key: str, *, tenant_id: int | None = None) -> list[str]:
        return agent_config_effective.effective_string_list(key, tenant_id=tenant_id)

    @staticmethod
    def list_agent_policies(*, tenant_id=None, user_id=None, agent_id=None):
        try:
            return agent_access_policy_store.list_agent_policies(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
            )
        except RuntimeError:
            return []


subagent_catalog.register_subagent_catalog_dependencies(_SubagentCatalogDeps())
access.register_agent_access_dependencies(_SubagentCatalogDeps())

AgentRegistry = domain.AgentRegistry
effective_tool_names_for_caller = domain.effective_tool_names_for_caller
get_agent_registry = domain.get_agent_registry
resolve_agent_tool_names = domain.resolve_agent_tool_names
