"""Agent turn hooks — dispatch by ``tool_discipline_preset`` from agent plugins (not agent_id in planner)."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from apps.backend.domain.agent_runtime.agent_behavior import _agent_behavior_flags

logger = logging.getLogger(__name__)


class AgentTurnHooks(Protocol):
    def prepare_tool_context(
        self, tool_context: dict[str, Any], *, ranking_user_text: str | None
    ) -> None: ...

    def apply_payload_tool_choice(
        self,
        payload_base: dict[str, Any],
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
        max_rounds: int,
    ) -> None: ...

    def recover_tool_calls_from_message(
        self,
        msg: dict[str, Any],
        *,
        allowed_tool_names: set[str] | frozenset[str],
        tools_for_round: list[Any],
    ) -> list[dict[str, Any]] | None: ...

    def sanitize_completion(self, data: dict[str, Any]) -> bool: ...

    def maybe_nudge_text_only_turn(
        self,
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
    ) -> str | None: ...

    def on_tool_done(
        self,
        tool_context: dict[str, Any],
        *,
        name: str,
        result: str,
        ok_sum: bool | None,
    ) -> dict[str, Any]: ...


class _NoopTurnHooks:
    def prepare_tool_context(
        self, tool_context: dict[str, Any], *, ranking_user_text: str | None
    ) -> None:
        return None

    def apply_payload_tool_choice(
        self,
        payload_base: dict[str, Any],
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
        max_rounds: int,
    ) -> None:
        return None

    def recover_tool_calls_from_message(
        self,
        msg: dict[str, Any],
        *,
        allowed_tool_names: set[str] | frozenset[str],
        tools_for_round: list[Any],
    ) -> list[dict[str, Any]] | None:
        if not tools_for_round:
            return None
        from apps.backend.domain.tools.call_content_recovery import (
            recover_tool_calls_from_assistant_content,
        )

        return recover_tool_calls_from_assistant_content(
            msg,
            allowed_tool_names=allowed_tool_names,
        )

    def sanitize_completion(self, data: dict[str, Any]) -> bool:
        return False

    def maybe_nudge_text_only_turn(
        self,
        tool_context: dict[str, Any],
        *,
        allowed_names: set[str] | frozenset[str],
        round_i: int,
    ) -> str | None:
        return None

    def on_tool_done(
        self,
        tool_context: dict[str, Any],
        *,
        name: str,
        result: str,
        ok_sum: bool | None,
    ) -> dict[str, Any]:
        return {}


def turn_hooks_for_agent(agent_id: str | None) -> AgentTurnHooks:
    """Resolve turn hooks from agent plugin ``tool_discipline_preset``."""
    preset = _agent_behavior_flags(agent_id).get("tool_discipline_preset")
    if preset == "dashboard":
        from apps.backend.domain.agent_runtime.dashboard_guards import DashboardTurnHooks

        return DashboardTurnHooks()
    return _NoopTurnHooks()
