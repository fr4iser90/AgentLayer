"""Unattended + git: bash policy and git_sync pull semantics.

Agent-level repeat-pull pre-block (_unattended_blocked_tool_json /
_unattended_mark_git_pull_done) was removed; these tests cover what still applies.
"""

from __future__ import annotations

import json

from apps.backend.domain import agent as agent_mod
from apps.backend.domain.coding.bash_policy import unattended_coding_bash_reject_reason
from plugins.tools.integrations.github.git_sync import _classify_pull_output, _pull_next_steps


def test_agent_does_not_preblock_repeat_git_sync_pull() -> None:
    """Repeat pull is allowed at agent loop (no schedule_git_pull_done gate)."""
    assert not hasattr(agent_mod, "_unattended_blocked_tool_json")
    assert not hasattr(agent_mod, "_unattended_mark_git_pull_done")


def test_unattended_bash_allows_git_pull_ff_only() -> None:
    assert unattended_coding_bash_reject_reason("git pull --ff-only") is None
    assert unattended_coding_bash_reject_reason("git pull") is None


def test_unattended_bash_rejects_prose_not_pull() -> None:
    assert unattended_coding_bash_reject_reason("Now I need to:") is not None


def test_git_sync_pull_classify_and_next_steps() -> None:
    """Tool-level pull_result + next_steps (formerly consumed by mark_git_pull_done)."""
    assert _classify_pull_output("Already up to date.\n", 0) == "already_up_to_date"
    steps = _pull_next_steps("already_up_to_date")
    assert any("do not" in s.lower() for s in steps)


def test_git_sync_pull_success_payload_shape() -> None:
    """Structured ok payload shape schedule jobs / models expect."""
    payload = {
        "ok": True,
        "operation": "pull",
        "pull_result": "already_up_to_date",
        "message": "Repository is up to date with remote.",
        "next_steps": ["Do not pull again"],
    }
    raw = json.dumps(payload)
    o = json.loads(raw)
    assert o["ok"] is True
    assert o.get("pull_result") == "already_up_to_date"
    assert o.get("operation") == "pull"
