"""Infrastructure adapter for plugin tool routing settings."""

from __future__ import annotations

from apps.backend.domain.plugin_system import tool_routing as domain
from apps.backend.infrastructure import agent_config_effective


class _ToolRoutingDeps:
    @staticmethod
    def effective_bool(key: str, *, default: bool) -> bool:
        return agent_config_effective.effective_bool(key, default=default)


domain.register_tool_routing_dependencies(_ToolRoutingDeps())

TOOL_DOMAIN_SHARED = domain.TOOL_DOMAIN_SHARED
TOOL_INTROSPECTION = domain.TOOL_INTROSPECTION
classify_user_tool_categories = domain.classify_user_tool_categories
classify_user_tool_category = domain.classify_user_tool_category
filter_merged_tools_by_categories = domain.filter_merged_tools_by_categories
filter_merged_tools_by_categories_for_agent = domain.filter_merged_tools_by_categories_for_agent
filter_merged_tools_by_category = domain.filter_merged_tools_by_category
filter_merged_tools_by_domain = domain.filter_merged_tools_by_domain
last_user_text = domain.last_user_text
