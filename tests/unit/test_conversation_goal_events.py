"""WebSocket event mapping for session harness tool results."""

from __future__ import annotations

import json

from apps.backend.application.agent_runtime.use_cases.conversation_goal_events import (
    conversation_goal_websocket_events,
)


def test_plan_mode_set_emits_plan_mode_event() -> None:
    result = json.dumps({"ok": True, "plan_mode": True, "plan_event": "on"})
    events = conversation_goal_websocket_events("plan_mode_set", result)
    assert len(events) == 1
    assert events[0]["type"] == "agent.plan_mode"
    assert events[0]["plan_mode"] is True
    assert events[0]["plan_event"] == "on"


def test_exit_plan_mode_emits_plan_mode_with_plan() -> None:
    result = json.dumps(
        {
            "ok": True,
            "plan_mode": False,
            "plan": "# Plan\n\nDo step one.",
            "plan_event": "exit",
        }
    )
    events = conversation_goal_websocket_events("exit_plan_mode", result)
    assert len(events) == 1
    assert events[0]["type"] == "agent.plan_mode"
    assert events[0]["plan_mode"] is False
    assert events[0]["plan"] == "# Plan\n\nDo step one."
    assert events[0]["plan_event"] == "exit"


def test_goal_create_emits_goal_event() -> None:
    goal = {"id": "g1", "objective": "Ship", "phase": "active"}
    result = json.dumps({"ok": True, "goal": goal, "goal_event": "create"})
    events = conversation_goal_websocket_events("goal_create", result)
    assert len(events) == 1
    assert events[0]["type"] == "agent.goal"
    assert events[0]["goal"] == goal


def test_todo_write_emits_todos_event() -> None:
    todos = [{"content": "A", "status": "pending"}]
    counts = {"pending": 1, "in_progress": 0, "completed": 0}
    result = json.dumps({"ok": True, "todos": todos, "counts": counts, "todos_event": "write"})
    events = conversation_goal_websocket_events("todo_write", result)
    assert len(events) == 1
    assert events[0]["type"] == "agent.todos"
    assert events[0]["todos"] == todos
    assert events[0]["counts"] == counts


def test_unknown_tool_returns_empty() -> None:
    assert conversation_goal_websocket_events("bash", '{"ok": true}') == []


def test_invalid_json_returns_empty() -> None:
    assert conversation_goal_websocket_events("plan_mode_set", "not-json") == []


def test_ok_false_returns_empty() -> None:
    assert conversation_goal_websocket_events("plan_mode_set", json.dumps({"ok": False})) == []
