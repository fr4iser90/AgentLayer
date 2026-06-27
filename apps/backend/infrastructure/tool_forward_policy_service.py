"""Infrastructure adapter for tool forward context budgeting."""

from __future__ import annotations

from typing import Any

from apps.backend.domain import tool_forward_policy as domain
from apps.backend.infrastructure.context_budget import completion_quotas_from_window


class _ToolForwardPolicyDeps:
    @staticmethod
    def completion_quotas_from_window(window: int, *, source: str) -> Any:
        return completion_quotas_from_window(window, source=source)


domain.register_tool_forward_policy_dependencies(_ToolForwardPolicyDeps())

ToolForwardContext = domain.ToolForwardContext
ToolForwardPlan = domain.ToolForwardPlan
build_tool_forward_plan = domain.build_tool_forward_plan
build_tool_triggers_map = domain.build_tool_triggers_map
compute_tool_forward_limits = domain.compute_tool_forward_limits
