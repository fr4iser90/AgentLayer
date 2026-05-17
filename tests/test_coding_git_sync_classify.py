"""Tests for structured coding_git_sync pull responses."""

from __future__ import annotations

from plugins.tools.capabilities.coding.coding_git_sync import (
    _classify_pull_output,
    _pull_next_steps,
)


def test_classify_already_up_to_date() -> None:
    assert _classify_pull_output("Already up to date.\n", 0) == "already_up_to_date"


def test_classify_failed() -> None:
    assert _classify_pull_output("error: merge conflict", 1) == "failed"


def test_pull_next_steps_mention_no_repeat() -> None:
    steps = _pull_next_steps("already_up_to_date")
    assert any("do not" in s.lower() for s in steps)
