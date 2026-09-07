"""Goal round driver emits optional continuation after agent turns."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

from apps.backend.application.agent_runtime.use_cases.goal_round_driver import (
    maybe_emit_goal_round,
)
from apps.backend.domain.agent_runtime.conversation_goal import new_goal


def _run(coro):
    return asyncio.run(coro)


def test_maybe_emit_goal_round_noop_without_event_emit() -> None:
    ctx: dict = {"conversation_id": str(uuid.uuid4())}
    _run(
        maybe_emit_goal_round(
            event_emit=None,
            tool_context=ctx,
            agent_run_id="run-1",
            round_num=1,
        )
    )
    assert "goal_round_emitted" not in ctx


def test_maybe_emit_goal_round_skips_when_already_emitted() -> None:
    emitted: list[dict] = []

    async def emit(ev: dict) -> None:
        emitted.append(ev)

    ctx = {"conversation_id": str(uuid.uuid4()), "goal_round_emitted": True}
    uid = uuid.uuid4()
    with patch(
        "apps.backend.domain.shared.identity.get_identity",
        return_value=(None, uid),
    ):
        _run(
            maybe_emit_goal_round(
                event_emit=emit,
                tool_context=ctx,
                agent_run_id="run-1",
                round_num=1,
            )
        )
    assert emitted == []


def test_maybe_emit_goal_round_emits_continue_when_active_goal() -> None:
    emitted: list[dict] = []
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    goal = new_goal(objective="Finish docs", max_goal_rounds=5)
    bumped_goal = {**goal, "rounds_started": 1, "revision": 2}

    async def emit(ev: dict) -> None:
        emitted.append(ev)

    ctx = {"conversation_id": str(conv_id)}
    with (
        patch(
            "apps.backend.domain.shared.identity.get_identity",
            return_value=(None, user_id),
        ),
        patch(
            "apps.backend.application.agent_runtime.use_cases.goal_round_driver.store.get_conversation_goal",
            return_value={"goal": goal, "todos": [], "plan_mode": False},
        ),
        patch(
            "apps.backend.application.agent_runtime.use_cases.goal_round_driver.store.bump_goal_round",
            return_value={"goal": bumped_goal, "todos": [], "plan_mode": False},
        ),
    ):
        _run(
            maybe_emit_goal_round(
                event_emit=emit,
                tool_context=ctx,
                agent_run_id="run-42",
                round_num=2,
            )
        )

    assert len(emitted) == 1
    ev = emitted[0]
    assert ev["type"] == "agent.goal_round"
    assert ev["continue"] is True
    assert ev["agent_run_id"] == "run-42"
    assert ev["round"] == 1
    assert ev["max_goal_rounds"] == 5
    assert ev["source_round"] == 2
    assert "Finish docs" in ev["prompt"]
    assert ctx["goal_round_emitted"] is True


def test_maybe_emit_goal_round_stops_at_max_rounds() -> None:
    emitted: list[dict] = []
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    goal = new_goal(objective="Finish docs", max_goal_rounds=2)
    goal["rounds_started"] = 2

    async def emit(ev: dict) -> None:
        emitted.append(ev)

    ctx = {"conversation_id": str(conv_id)}
    with (
        patch(
            "apps.backend.domain.shared.identity.get_identity",
            return_value=(None, user_id),
        ),
        patch(
            "apps.backend.application.agent_runtime.use_cases.goal_round_driver.store.get_conversation_goal",
            return_value={"goal": goal, "todos": [], "plan_mode": False},
        ),
    ):
        _run(
            maybe_emit_goal_round(
                event_emit=emit,
                tool_context=ctx,
                agent_run_id="run-1",
                round_num=1,
            )
        )

    assert len(emitted) == 1
    assert emitted[0]["continue"] is False
    assert emitted[0]["reason"] == "max_rounds"
    assert ctx["goal_round_emitted"] is True


def test_maybe_emit_goal_round_skips_paused_goal() -> None:
    emitted: list[dict] = []
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    goal = new_goal(objective="Finish docs")
    goal["phase"] = "paused"

    async def emit(ev: dict) -> None:
        emitted.append(ev)

    ctx = {"conversation_id": str(conv_id)}
    with (
        patch(
            "apps.backend.domain.shared.identity.get_identity",
            return_value=(None, user_id),
        ),
        patch(
            "apps.backend.application.agent_runtime.use_cases.goal_round_driver.store.get_conversation_goal",
            return_value={"goal": goal, "todos": [], "plan_mode": False},
        ),
    ):
        _run(
            maybe_emit_goal_round(
                event_emit=emit,
                tool_context=ctx,
                agent_run_id="run-1",
                round_num=1,
            )
        )

    assert emitted == []
    assert "goal_round_emitted" not in ctx
