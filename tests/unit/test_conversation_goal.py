"""Unit tests for session harness goal/todo domain."""

from __future__ import annotations

import pytest

from apps.backend.domain.agent_runtime.conversation_goal import (
    PLAN_MODE_GUIDANCE,
    apply_goal_update,
    goal_round_prompt,
    new_goal,
    normalize_todos,
    conversation_goal_prompt_block,
    todo_counts,
)

_ALL_HARNESS_TOOLS = (
    "goal_get",
    "goal_create",
    "goal_update",
    "todo_write",
    "todo_read",
    "plan_mode_set",
    "exit_plan_mode",
)


def test_new_goal_and_update_cycle() -> None:
    g = new_goal(objective="Ship the feature")
    assert g["phase"] == "active"
    assert g["revision"] == 1
    g2 = apply_goal_update(
        g, goal_id=g["id"], revision=1, action="pause"
    )
    assert g2["phase"] == "paused"
    assert g2["revision"] == 2
    g3 = apply_goal_update(
        g2, goal_id=g["id"], revision=2, action="complete"
    )
    assert g3["phase"] == "completed"


def test_goal_revision_mismatch() -> None:
    g = new_goal(objective="x")
    with pytest.raises(ValueError, match="revision"):
        apply_goal_update(g, goal_id=g["id"], revision=99, action="pause")


def test_todo_write_normalizes_and_counts() -> None:
    todos = normalize_todos(
        [
            {"content": "A", "status": "in_progress"},
            {"content": "B", "status": "pending"},
            {"content": "C", "status": "completed"},
        ]
    )
    assert todo_counts(todos) == {"pending": 1, "in_progress": 1, "completed": 1}
    with pytest.raises(ValueError, match="in_progress"):
        normalize_todos(
            [
                {"content": "A", "status": "in_progress"},
                {"content": "B", "status": "in_progress"},
            ]
        )


def test_plan_mode_guidance_and_goal_round_prompt() -> None:
    assert "exit_plan_mode" in PLAN_MODE_GUIDANCE
    prompt = goal_round_prompt(
        objective="Ship it",
        round_no=2,
        max_rounds=8,
        todos_summary="1 in_progress, 0 pending, 0 completed",
    )
    assert "Goal round 2/8" in prompt
    assert "Ship it" in prompt
    assert "goal_update" in prompt


def test_prompt_block_empty_without_harness_tools() -> None:
    assert conversation_goal_prompt_block(tool_names=["bash", "edit"]) == ""
    assert conversation_goal_prompt_block(tool_names=[]) == ""


def test_prompt_block_prompts_for_a_goal_when_none_exists() -> None:
    block = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS)
    assert "No ongoing goal" in block
    assert "goal_create" in block
    assert "No session todos" in block
    assert "todo_write" in block


def test_prompt_block_renders_goal_state_with_optimistic_lock() -> None:
    goal = new_goal(objective="Ship the harness")
    goal["rounds_started"] = 3
    block = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS, goal=goal)
    assert "Ship the harness" in block
    assert f"goal_id={goal['id']}" in block
    assert "revision=1" in block
    assert "round 3/32" in block
    assert "No ongoing goal" not in block


def test_prompt_block_renders_todo_checklist() -> None:
    todos = normalize_todos(
        [
            {"content": "Read the code", "status": "completed"},
            {"content": "Write the fix", "status": "in_progress"},
            {"content": "Run tests", "status": "pending"},
        ]
    )
    block = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS, todos=todos)
    assert "- [x] Read the code" in block
    assert "- [>] Write the fix" in block
    assert "- [ ] Run tests" in block


def test_prompt_block_scopes_sections_to_available_tools() -> None:
    todo_only = conversation_goal_prompt_block(tool_names=["todo_write", "todo_read"])
    assert "todo_write" in todo_only
    assert "goal_create" not in todo_only

    goal_only = conversation_goal_prompt_block(tool_names=["goal_get"])
    assert "goal_create" in goal_only
    assert "todo_write" not in goal_only


def test_prompt_block_includes_plan_guidance_only_when_plan_mode_active() -> None:
    off = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS, plan_mode=False)
    assert PLAN_MODE_GUIDANCE not in off
    on = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS, plan_mode=True)
    assert PLAN_MODE_GUIDANCE in on
    # Agents without the plan tools must not be told to call exit_plan_mode.
    no_plan_tools = conversation_goal_prompt_block(
        tool_names=["goal_get", "todo_write"], plan_mode=True
    )
    assert PLAN_MODE_GUIDANCE not in no_plan_tools


def test_prompt_block_reports_blocked_goal_reason() -> None:
    goal = new_goal(objective="Ship it")
    blocked = apply_goal_update(
        goal,
        goal_id=goal["id"],
        revision=1,
        action="blocked",
        blocked_reason="missing GitHub token",
    )
    block = conversation_goal_prompt_block(tool_names=_ALL_HARNESS_TOOLS, goal=blocked)
    assert "missing GitHub token" in block
    assert "resume" in block
