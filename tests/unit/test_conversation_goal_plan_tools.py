"""Conversation plan-mode tool handlers."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from plugins.tools.platform.conversation_goal.goal_todos import (
    exit_plan_mode,
    plan_mode_set,
)


def _conv_context(conv_id: uuid.UUID | None = None) -> dict:
    return {"conversation_id": str(conv_id or uuid.uuid4())}


@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_plan_mode_set_requires_identity(mock_ident) -> None:
    mock_ident.return_value = (None, None)
    out = json.loads(plan_mode_set({"active": True}, _conv_context()))
    assert out["ok"] is False


@patch("plugins.tools.platform.conversation_goal.goal_todos.store.set_plan_mode")
@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_plan_mode_set_requires_boolean_active(mock_ident, mock_set) -> None:
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_ident.return_value = (None, user_id)
    out = json.loads(
        plan_mode_set({"active": "yes"}, {"conversation_id": str(conv_id)})
    )
    assert out["ok"] is False
    assert "boolean" in out["error"]
    mock_set.assert_not_called()


@patch("plugins.tools.platform.conversation_goal.goal_todos.store.set_plan_mode")
@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_plan_mode_set_turns_on(mock_ident, mock_set) -> None:
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_ident.return_value = (None, user_id)
    mock_set.return_value = {"goal": None, "todos": [], "plan_mode": True}
    out = json.loads(
        plan_mode_set({"active": True}, {"conversation_id": str(conv_id)})
    )
    assert out["ok"] is True
    assert out["plan_mode"] is True
    assert out["ws_event"] == "agent.plan_mode"
    assert out["plan_event"] == "on"
    mock_set.assert_called_once_with(user_id, conv_id, True)


@patch("plugins.tools.platform.conversation_goal.goal_todos.store.set_plan_mode")
@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_exit_plan_mode_requires_markdown_heading(mock_ident, mock_set) -> None:
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_ident.return_value = (None, user_id)
    out = json.loads(
        exit_plan_mode({"plan": "plain text only"}, {"conversation_id": str(conv_id)})
    )
    assert out["ok"] is False
    assert "heading" in out["error"]
    mock_set.assert_not_called()


@patch("plugins.tools.platform.conversation_goal.goal_todos.store.get_conversation_goal")
@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_exit_plan_mode_requires_active_plan_mode(mock_ident, mock_get) -> None:
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_ident.return_value = (None, user_id)
    mock_get.return_value = {"goal": None, "todos": [], "plan_mode": False}
    out = json.loads(
        exit_plan_mode({"plan": "# Plan\n\nStep 1"}, {"conversation_id": str(conv_id)})
    )
    assert out["ok"] is False
    assert "not active" in out["error"]


@patch("plugins.tools.platform.conversation_goal.goal_todos.store.set_plan_mode")
@patch("plugins.tools.platform.conversation_goal.goal_todos.store.get_conversation_goal")
@patch("plugins.tools.platform.conversation_goal.goal_todos.get_identity")
def test_exit_plan_mode_success(mock_ident, mock_get, mock_set) -> None:
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_ident.return_value = (None, user_id)
    mock_get.return_value = {"goal": None, "todos": [], "plan_mode": True}
    mock_set.return_value = {"goal": None, "todos": [], "plan_mode": False}
    plan = "# Rollout\n\n1. Ship\n2. Monitor"
    out = json.loads(
        exit_plan_mode({"plan": plan}, {"conversation_id": str(conv_id)})
    )
    assert out["ok"] is True
    assert out["plan_mode"] is False
    assert out["plan"] == plan
    assert out["ws_event"] == "agent.plan_mode"
    assert out["plan_event"] == "exit"
    mock_set.assert_called_once_with(user_id, conv_id, False)
