"""Tests for ``git_sync`` (workspace git pull / fetch)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from plugins.tools.integrations.github.git_sync import git_sync


def _git_init_commit(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True, capture_output=True)
    (root / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def test_coding_git_sync_not_a_repo(tmp_path: Path) -> None:
    ctx = {"workspace": {"path": str(tmp_path)}}
    out = git_sync({"operation": "pull"}, context=ctx)
    data = json.loads(out)
    assert data["ok"] is False
    assert "git" in (data.get("error") or "").lower()


def test_coding_git_sync_invalid_operation(tmp_path: Path) -> None:
    _git_init_commit(tmp_path)
    ctx = {"workspace": {"path": str(tmp_path)}}
    out = git_sync({"operation": "push"}, context=ctx)
    data = json.loads(out)
    assert data["ok"] is False


def test_coding_git_sync_fetch_no_remote(tmp_path: Path) -> None:
    _git_init_commit(tmp_path)
    ctx = {"workspace": {"path": str(tmp_path)}}
    out = git_sync({"operation": "fetch"}, context=ctx)
    data = json.loads(out)
    assert "exit_code" in data
    assert "output" in data


def test_coding_git_sync_pull_default_includes_branch_and_pull_result(tmp_path: Path) -> None:
    """Regression: _current_branch must not unpack 3-tuple from 2-tuple _run_git."""
    _git_init_commit(tmp_path)
    ctx = {"workspace": {"path": str(tmp_path)}}
    out = git_sync({}, context=ctx)
    data = json.loads(out)
    assert "branch" in data
    assert data.get("branch") in ("master", "main")
    assert data.get("pull_result") in ("already_up_to_date", "completed", "fast_forward", "failed")
    assert "message" in data
    assert "not enough values to unpack" not in out
