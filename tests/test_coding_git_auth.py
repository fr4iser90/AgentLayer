"""Tests for shared GitHub PAT helpers."""

from __future__ import annotations

from plugins.tools.capabilities.coding.coding_git_auth import (
    git_auth_failure_reason,
    git_command_needs_github_pat,
    no_github_pat_payload,
)


def test_git_command_needs_pat() -> None:
    assert git_command_needs_github_pat("git push -u origin main")
    assert git_command_needs_github_pat("cd x && git pull")
    assert not git_command_needs_github_pat("git status")
    assert not git_command_needs_github_pat("ls -la")


def test_git_auth_failure_reason() -> None:
    assert git_auth_failure_reason("remote: Permission denied", 1) == "auth_denied"
    assert git_auth_failure_reason("ok", 0) is None


def test_no_github_pat_payload_has_reason() -> None:
    p = no_github_pat_payload()
    assert p["reason"] == "no_token"
    assert "github_pat" in p["error"]
