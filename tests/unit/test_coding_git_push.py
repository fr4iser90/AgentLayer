"""Tests for git_push and git push blocking in bash."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from plugins.tools.workspace.shell.bash import bash
from plugins.tools.integrations.github.lib.auth import parse_github_pat, redact_secrets
from plugins.tools.integrations.github.git_push import git_push


def test_parse_github_pat_string_and_json() -> None:
    assert parse_github_pat("ghp_abc") == "ghp_abc"
    assert parse_github_pat('{"token":"ghp_xyz"}') == "ghp_xyz"


def test_redact_secrets() -> None:
    assert "ghp_secret" not in redact_secrets("error ghp_secret here", "ghp_secret")


def test_coding_bash_git_push_no_token(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ctx = {"workspace": {"path": str(repo), "id": "ws-1"}}
    with patch(
        "plugins.tools.workspace.shell.bash.github_pat_for_current_user",
        return_value=None,
    ):
        out = json.loads(bash({"command": "git push -u origin main"}, context=ctx))
    assert out["ok"] is False
    assert out["reason"] == "no_token"


def test_coding_bash_git_push_injects_askpass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    tok = "ghp_test_token_never_in_output"

    def fake_run(cmd, **kwargs):
        assert kwargs.get("env", {}).get("GIT_ASKPASS")
        return subprocess.CompletedProcess(cmd, 0, stdout="pushed\n", stderr="")

    ctx = {"workspace": {"path": str(repo), "id": "ws-1"}}
    with (
        patch(
            "plugins.tools.workspace.shell.bash.github_pat_for_current_user",
            return_value=tok,
        ),
        patch("plugins.tools.workspace.shell.bash.subprocess.run", side_effect=fake_run),
    ):
        raw = bash({"command": "git push origin main"}, context=ctx)
    out = json.loads(raw)
    assert out["ok"] is True
    assert out.get("github_auth") == "pat_injected"
    assert tok not in raw


def test_coding_git_push_no_workspace() -> None:
    out = json.loads(git_push({}, context={}))
    assert out["ok"] is False


def test_coding_git_push_no_token(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    ctx = {"workspace": {"path": str(repo), "id": "ws-1"}}
    with patch(
        "plugins.tools.integrations.github.git_push.github_pat_for_current_user",
        return_value=None,
    ):
        out = json.loads(git_push({}, context=ctx))
    assert out["ok"] is False
    assert out["reason"] == "no_token"


def test_coding_git_push_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    def fake_run(cmd, **kwargs):
        assert "push" in cmd
        assert kwargs.get("env", {}).get("GIT_ASKPASS")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    ctx = {"workspace": {"path": str(repo), "id": "ws-1"}}
    tok = "ghp_test_token_do_not_leak"
    with (
        patch(
            "plugins.tools.integrations.github.git_push.github_pat_for_current_user",
            return_value=tok,
        ),
        patch(
            "plugins.tools.integrations.github.git_push._current_branch",
            return_value="feature/x",
        ),
        patch("plugins.tools.integrations.github.git_push.subprocess.run", side_effect=fake_run),
    ):
        raw = git_push({"remote": "origin"}, context=ctx)
    out = json.loads(raw)
    assert out["ok"] is True
    assert tok not in raw


def test_coding_agent_registry_includes_git_push() -> None:
    from apps.backend.domain.agent_runtime.registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    assert "git_push" in a["tool_names"]
