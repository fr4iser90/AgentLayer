"""Agent behavior flags derived from agent definitions."""
from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_runtime.registry import get_agent_registry


def _agent_behavior_flags(agent_id: str | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "strict_workspace": False,
        "tool_discipline_preset": None,
    }
    if not agent_id or not str(agent_id).strip():
        return base
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return base
    preset = ag.get("tool_discipline_preset")
    preset_norm = preset.strip().lower() if isinstance(preset, str) and preset.strip() else None
    return {
        "strict_workspace": bool(ag.get("strict_workspace")),
        "tool_discipline_preset": preset_norm,
    }
