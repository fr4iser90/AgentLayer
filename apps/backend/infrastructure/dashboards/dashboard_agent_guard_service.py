"""Infrastructure adapter for dashboard agent guard hooks."""

from __future__ import annotations

from apps.backend.domain.agent_runtime import dashboard_guards as domain
from apps.backend.infrastructure.plugins.skill_plugins import load_skill_text_by_id


class _DashboardAgentGuardDeps:
    load_skill_text_by_id = staticmethod(load_skill_text_by_id)


domain.register_dashboard_agent_guard_dependencies(_DashboardAgentGuardDeps())

DashboardTurnHooks = domain.DashboardTurnHooks
dashboard_layout_proposal_nudge_needed = domain.dashboard_layout_proposal_nudge_needed
is_propose_layouts_tool = domain.is_propose_layouts_tool
layout_proposal_intent = domain.layout_proposal_intent
layout_proposal_nudge_needed = domain.layout_proposal_nudge_needed
