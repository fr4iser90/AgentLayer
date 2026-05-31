"""Unattended sub-agent shell command validation (delegates to coding_bash_policy)."""

from __future__ import annotations

from apps.backend.domain.agent import _blocked_tool_json
from apps.backend.domain.coding.bash_policy import (
    unattended_coding_bash_reject_reason,
)


def test_unattended_policy_accepts_ls_with_flags() -> None:
    assert unattended_coding_bash_reject_reason("ls -la") is None
    assert unattended_coding_bash_reject_reason("ls -la /code") is None
    assert unattended_coding_bash_reject_reason("head -n 50 foo.py") is None


def test_unattended_coding_bash_not_blocked_for_ls() -> None:
    ctx = {"agent_unattended": True, "agent_id": "coding"}
    blocked = _blocked_tool_json("bash", {"command": "ls -la"}, ctx)
    assert blocked is None


def test_unattended_rejects_prose() -> None:
    assert unattended_coding_bash_reject_reason("Now I need to:") is not None
