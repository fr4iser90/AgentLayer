"""Dashboard ``tool_discipline_preset`` turn hooks — not tool-forward policy, not agent_planner."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from apps.backend.domain.tools.forward_policy import build_tool_triggers_map

logger = logging.getLogger(__name__)


class DashboardAgentGuardDependencies(Protocol):
    def load_skill_text_by_id(self, skill_id: str) -> str | None: ...


_deps: DashboardAgentGuardDependencies | None = None


def register_dashboard_agent_guard_dependencies(deps: DashboardAgentGuardDependencies) -> None:
    global _deps
    _deps = deps


def load_skill_text_by_id(skill_id: str) -> str | None:
    return _deps.load_skill_text_by_id(skill_id) if _deps is not None else None


def is_propose_layouts_tool(name: str) -> bool:
    n = (name or "").strip()
    return n == "propose_layouts" or n.endswith(".propose_layouts")


def layout_proposal_intent(user_text: str) -> bool:
    """True when user text matches ``propose_layouts`` plugin domain triggers."""
    tl = (user_text or "").lower()
    if not tl:
        return False
    triggers = build_tool_triggers_map(["propose_layouts"]).get("propose_layouts", ())
    return any(tr in tl for tr in triggers)


def layout_proposal_nudge_needed(
    *,
    layout_proposal_required: bool,
    propose_layouts_done: bool,
    nudge_count: int,
    forwarded_tool_names: set[str] | frozenset[str],
    max_nudges: int = 2,
) -> bool:
    if not layout_proposal_required or propose_layouts_done:
        return False
    if nudge_count >= max(1, int(max_nudges)):
        return False
    return "propose_layouts" in forwarded_tool_names


class DashboardTurnHooks:
    """Hooks for agents with ``tool_discipline_preset: dashboard`` in agent.yaml."""

    def prepare_tool_context(
        self, tool_context: dict[str, Any], *, ranking_user_text: str | None
    ) -> None:
        if (ranking_user_text or "").strip():
            tool_context["dashboard_layout_proposal_required"] = layout_proposal_intent(
                ranking_user_text or ""
            )

    def apply_payload_tool_choice(
        self,
        payload_base: dict[str, Any],
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
        max_rounds: int,
    ) -> None:
        if not tool_context.pop("_force_tool_choice_propose_layouts", False):
            return
        if "propose_layouts" not in allowed_names:
            return
        payload_base["tool_choice"] = {
            "type": "function",
            "function": {"name": "propose_layouts"},
        }
        logger.info(
            "dashboard turn hook: tool_choice=propose_layouts (round %d/%d)",
            round_i + 1,
            max_rounds,
        )

    def recover_tool_calls_from_message(
        self,
        msg: dict[str, Any],
        *,
        allowed_tool_names: set[str] | frozenset[str],
        tools_for_round: list[Any],
    ) -> list[dict[str, Any]] | None:
        if not tools_for_round:
            return None
        from apps.backend.domain.agent_runtime.assistant_display import (
            synthetic_dashboard_tool_calls_from_message,
        )

        return synthetic_dashboard_tool_calls_from_message(
            msg,
            allowed_tool_names=allowed_tool_names,
        )

    def sanitize_completion(self, data: dict[str, Any]) -> bool:
        from apps.backend.domain.agent_runtime.assistant_display import (
            sanitize_completion_for_dashboard_agent,
        )

        return sanitize_completion_for_dashboard_agent(data)

    def maybe_nudge_text_only_turn(
        self,
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
    ) -> str | None:
        nudges = int(tool_context.get("dashboard_layout_proposal_nudges") or 0)
        if not layout_proposal_nudge_needed(
            layout_proposal_required=bool(
                tool_context.get("dashboard_layout_proposal_required")
            ),
            propose_layouts_done=bool(tool_context.get("dashboard_propose_layouts_done")),
            nudge_count=nudges,
            forwarded_tool_names=allowed_names,
        ):
            return None
        tool_context["dashboard_layout_proposal_nudges"] = nudges + 1
        tool_context["_force_tool_choice_propose_layouts"] = True
        logger.info(
            "dashboard turn hook: rejected text-only round %d — nudge %d, forcing propose_layouts",
            round_i + 1,
            nudges + 1,
        )
        return load_skill_text_by_id("dashboard_layout_proposal_nudge") or ""

    def on_tool_done(
        self,
        tool_context: dict[str, Any],
        *,
        name: str,
        result: str,
        ok_sum: bool | None,
    ) -> dict[str, Any]:
        if not is_propose_layouts_tool(name) or not ok_sum:
            return {}
        tool_context["dashboard_propose_layouts_done"] = True
        extras: dict[str, Any] = {}
        try:
            prop = json.loads(result or "")
            if isinstance(prop, dict) and prop.get("proposal_set_id"):
                extras["proposal_set_id"] = str(prop["proposal_set_id"])
                if prop.get("dashboard_id"):
                    extras["dashboard_id"] = str(prop["dashboard_id"])
        except Exception:
            pass
        return extras


# Back-compat for tests / external imports
def dashboard_layout_proposal_nudge_needed(
    *,
    agent_id: str | None,
    layout_proposal_required: bool,
    propose_layouts_done: bool,
    nudge_count: int,
    forwarded_tool_names: set[str] | frozenset[str],
    max_nudges: int = 2,
) -> bool:
    if (agent_id or "").strip() != "dashboard":
        return False
    return layout_proposal_nudge_needed(
        layout_proposal_required=layout_proposal_required,
        propose_layouts_done=propose_layouts_done,
        nudge_count=nudge_count,
        forwarded_tool_names=forwarded_tool_names,
        max_nudges=max_nudges,
    )
