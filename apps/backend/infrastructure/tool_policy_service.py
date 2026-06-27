"""Infrastructure adapter for plugin tool policy settings."""

from __future__ import annotations

from apps.backend.domain.plugin_system import tool_policy as domain
from apps.backend.infrastructure.operator_settings import resolved_agent_mode


class _ToolPolicyDeps:
    resolved_agent_mode = staticmethod(resolved_agent_mode)


domain.register_tool_policy_dependencies(_ToolPolicyDeps())

effective_execution_context = domain.effective_execution_context
effective_flags = domain.effective_flags
filter_chat_tool_specs = domain.filter_chat_tool_specs
