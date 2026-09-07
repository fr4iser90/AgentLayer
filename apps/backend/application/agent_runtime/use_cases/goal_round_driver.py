"""Emit optional goal-round continuation after a successful agent turn."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.domain.agent_runtime.conversation_goal import goal_round_prompt, todo_counts
from apps.backend.infrastructure.agent_runtime import conversation_goal_store as store

logger = logging.getLogger(__name__)


async def maybe_emit_goal_round(
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    tool_context: dict[str, Any],
    agent_run_id: str,
    round_num: int,
) -> None:
    """If an active goal remains under max rounds, bump counter and ask the UI to continue."""
    if event_emit is None:
        return
    if tool_context.get("goal_round_emitted"):
        return
    cid_raw = tool_context.get("conversation_id")
    if not cid_raw:
        return
    try:
        conv_id = uuid.UUID(str(cid_raw).strip())
    except (ValueError, TypeError):
        return
    from apps.backend.domain.shared.identity import get_identity

    _tid, user_id = get_identity()
    if user_id is None:
        return
    try:
        row = store.get_conversation_goal(user_id, conv_id)
    except Exception:
        logger.exception("goal round: goal state load failed")
        return
    if not row:
        return
    goal = row.get("goal")
    if not isinstance(goal, dict):
        return
    if str(goal.get("phase") or "") != "active":
        return
    started = int(goal.get("rounds_started") or 0)
    max_rounds = int(goal.get("max_goal_rounds") or 32)
    if started >= max_rounds:
        await event_emit(
            {
                "type": "agent.goal_round",
                "agent_run_id": agent_run_id,
                "continue": False,
                "reason": "max_rounds",
                "goal": goal,
                "round": started,
                "max_goal_rounds": max_rounds,
            }
        )
        tool_context["goal_round_emitted"] = True
        return
    bumped = store.bump_goal_round(user_id, conv_id)
    goal_out = bumped.get("goal") if bumped else goal
    if not isinstance(goal_out, dict):
        return
    todos = bumped.get("todos") if bumped and isinstance(bumped.get("todos"), list) else []
    counts = todo_counts(todos)
    todos_summary = (
        f"{counts.get('in_progress', 0)} in_progress, "
        f"{counts.get('pending', 0)} pending, "
        f"{counts.get('completed', 0)} completed"
    )
    round_no = int(goal_out.get("rounds_started") or started + 1)
    prompt = goal_round_prompt(
        objective=str(goal_out.get("objective") or ""),
        round_no=round_no,
        max_rounds=max_rounds,
        todos_summary=todos_summary,
    )
    await event_emit(
        {
            "type": "agent.goal_round",
            "agent_run_id": agent_run_id,
            "continue": True,
            "prompt": prompt,
            "goal": goal_out,
            "round": round_no,
            "max_goal_rounds": max_rounds,
            "source_round": round_num,
        }
    )
    tool_context["goal_round_emitted"] = True
