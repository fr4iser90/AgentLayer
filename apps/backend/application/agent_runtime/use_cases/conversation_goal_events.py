"""Parse conversation goal/todo tool results into websocket events."""

from __future__ import annotations

import json
from typing import Any

_GOAL_TOOLS = frozenset({"goal_get", "goal_create", "goal_update"})
_TODO_TOOLS = frozenset({"todo_write", "todo_read"})
_PLAN_TOOLS = frozenset({"plan_mode_set", "exit_plan_mode"})


def conversation_goal_websocket_events(name: str, result: str | None) -> list[dict[str, Any]]:
    """Return zero or more WS payloads after a goal/todo tool completes."""
    if not result or name not in (_GOAL_TOOLS | _TODO_TOOLS | _PLAN_TOOLS):
        return []
    try:
        data = json.loads(result)
    except Exception:
        return []
    if not isinstance(data, dict) or not data.get("ok"):
        return []
    out: list[dict[str, Any]] = []
    if name in _GOAL_TOOLS:
        out.append(
            {
                "type": "agent.goal",
                "goal": data.get("goal"),
                "goal_event": data.get("goal_event") or name,
            }
        )
    if name in _TODO_TOOLS:
        todos = data.get("todos")
        if not isinstance(todos, list):
            todos = []
        counts = data.get("counts")
        if not isinstance(counts, dict):
            counts = {}
        out.append(
            {
                "type": "agent.todos",
                "todos": todos,
                "counts": counts,
                "todos_event": data.get("todos_event") or name,
            }
        )
    if name in _PLAN_TOOLS:
        out.append(
            {
                "type": "agent.plan_mode",
                "plan_mode": bool(data.get("plan_mode")),
                "plan_event": data.get("plan_event") or name,
                "plan": data.get("plan"),
            }
        )
    return out
