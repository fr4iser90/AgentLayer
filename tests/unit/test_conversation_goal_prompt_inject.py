"""Injection of the conversation goal/todo system block into the turn messages."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.application.agent_runtime.use_cases.chat_turn_preparation import (
    _agent_goal_tool_names,
    _inject_conversation_goal_block,
)
from apps.backend.domain.agent_runtime.conversation_goal import PLAN_MODE_GUIDANCE

_STORE = (
    "apps.backend.infrastructure.agent_runtime.conversation_goal_store.get_conversation_goal"
)
_REGISTRY = "apps.backend.domain.agent_runtime.registry.get_agent_registry"

_GOAL_TOOLS = [
    "goal_get",
    "goal_create",
    "goal_update",
    "todo_write",
    "todo_read",
    "plan_mode_set",
    "exit_plan_mode",
]


def _agent(tool_names: list[str]):
    class _Registry:
        @staticmethod
        def get_agent(_agent_id: str) -> dict:
            return {"tool_names": tool_names}

    return _Registry()


def _inject(messages: list[dict], *, agent_id: str | None = "coding") -> list[dict]:
    return _inject_conversation_goal_block(
        messages,
        agent_id=agent_id,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
    )


def _system_text(messages: list[dict]) -> str:
    return "\n".join(
        str(m.get("content") or "") for m in messages if m.get("role") == "system"
    )


class TestGoalToolDiscovery:
    @patch(_REGISTRY)
    def test_keeps_only_goal_tools(self, mock_reg) -> None:
        mock_reg.return_value = _agent(["bash", "edit", "todo_write", "goal_get"])
        assert _agent_goal_tool_names("coding") == frozenset({"todo_write", "goal_get"})

    @patch(_REGISTRY)
    def test_unknown_agent_has_none(self, mock_reg) -> None:
        class _Empty:
            @staticmethod
            def get_agent(_agent_id: str) -> None:
                return None

        mock_reg.return_value = _Empty()
        assert _agent_goal_tool_names("nope") == frozenset()

    def test_missing_agent_id_has_none(self) -> None:
        assert _agent_goal_tool_names(None) == frozenset()


class TestInjection:
    @patch(_STORE)
    @patch(_REGISTRY)
    def test_injects_goal_and_todo_state(self, mock_reg, mock_store) -> None:
        mock_reg.return_value = _agent(_GOAL_TOOLS)
        mock_store.return_value = {
            "goal": {
                "id": "g-1",
                "revision": 4,
                "objective": "Merge the goal layer",
                "phase": "active",
                "rounds_started": 2,
                "max_goal_rounds": 32,
            },
            "todos": [{"content": "Wire the prompt", "status": "in_progress"}],
            "plan_mode": False,
        }

        out = _inject([{"role": "user", "content": "go"}])
        text = _system_text(out)
        assert "Merge the goal layer" in text
        assert "goal_id=g-1" in text
        assert "revision=4" in text
        assert "- [>] Wire the prompt" in text

    @patch(_STORE)
    @patch(_REGISTRY)
    def test_agent_without_goal_tools_gets_nothing(self, mock_reg, mock_store) -> None:
        mock_reg.return_value = _agent(["bash", "edit"])
        mock_store.return_value = {"goal": None, "todos": [], "plan_mode": False}

        messages = [{"role": "user", "content": "go"}]
        assert _inject(messages) == messages

    @patch(_STORE)
    @patch(_REGISTRY)
    def test_agentless_chat_still_gets_plan_guidance(self, mock_reg, mock_store) -> None:
        mock_reg.return_value = _agent(_GOAL_TOOLS)
        mock_store.return_value = {"goal": None, "todos": [], "plan_mode": True}

        text = _system_text(_inject([{"role": "user", "content": "go"}], agent_id=None))
        assert PLAN_MODE_GUIDANCE in text
        # No tool list is known for agentless turns, so no goal/todo advertising.
        assert "goal_create" not in text

    @patch(_STORE)
    @patch(_REGISTRY)
    def test_missing_conversation_row_is_a_noop(self, mock_reg, mock_store) -> None:
        mock_reg.return_value = _agent(_GOAL_TOOLS)
        mock_store.return_value = None

        messages = [{"role": "user", "content": "go"}]
        assert _inject(messages) == messages
