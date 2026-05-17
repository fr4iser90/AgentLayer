"""Unattended schedule: block repeat pull and empty bash."""

from __future__ import annotations

import json

from apps.backend.domain.agent import (
    _unattended_blocked_tool_json,
    _unattended_mark_git_pull_done,
)


def test_block_repeat_git_sync_pull() -> None:
    ctx = {"agent_unattended": True, "schedule_git_pull_done": True, "schedule_git_pull_result": "already_up_to_date"}
    raw = _unattended_blocked_tool_json("coding_git_sync", {"operation": "pull"}, ctx)
    assert raw is not None
    o = json.loads(raw)
    assert o["ok"] is False
    assert "already completed" in o["error"].lower()


def test_block_repeat_bash_pull() -> None:
    ctx = {"agent_unattended": True, "schedule_git_pull_done": True, "schedule_git_pull_result": "already_up_to_date"}
    raw = _unattended_blocked_tool_json("coding_bash", {"command": "git pull --ff-only"}, ctx)
    assert raw is not None
    assert json.loads(raw)["ok"] is False


def test_mark_git_pull_done_sets_hint() -> None:
    ctx: dict = {"agent_unattended": True}
    result = json.dumps(
        {
            "ok": True,
            "operation": "pull",
            "pull_result": "already_up_to_date",
            "message": "Repository is up to date with remote.",
            "next_steps": ["Do not pull again"],
        }
    )
    hint = _unattended_mark_git_pull_done("coding_git_sync", result, ctx)
    assert hint is not None
    assert "Do NOT" in hint
    assert ctx.get("schedule_git_pull_done") is True
