"""Tests for workspace git read helpers (HTTP ``/git/changes`` backing)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from apps.backend.infrastructure.workspace_git import (
    parse_diff_stat_files,
    workspace_git_changes_summary,
    workspace_git_file_diff,
    workspace_git_has_changes,
)


def _have_git() -> bool:
    return shutil.which("git") is not None


def test_parse_diff_stat_files() -> None:
    raw = " hello.txt | 2 +-\n 2 files changed, 1 insertion(+), 1 deletion(-)\n"
    files = parse_diff_stat_files(raw)
    assert files == [{"path": "hello.txt", "stat": "2 +-"}]


@pytest.mark.skipif(not _have_git(), reason="git not installed")
def test_workspace_git_summary_and_file_diff(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "t@example.test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "test"],
        check=True,
        capture_output=True,
    )
    (root / "hello.txt").write_text("world\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "hello.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    assert workspace_git_has_changes(root) is False

    (root / "hello.txt").write_text("world2\n", encoding="utf-8")
    assert workspace_git_has_changes(root) is True

    summary = workspace_git_changes_summary(root)
    assert summary["ok"] is True
    assert summary["is_git_repo"] is True
    assert summary["has_changes"] is True
    assert any(f["path"] == "hello.txt" for f in summary["files"])

    diff = workspace_git_file_diff(root, "hello.txt")
    assert diff["ok"] is True
    assert "hello.txt" in diff["diff"]


def test_workspace_git_file_diff_rejects_unsafe_path(tmp_path: Path) -> None:
    if not _have_git():
        pytest.skip("git not installed")
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    out = workspace_git_file_diff(root, "../etc/passwd")
    assert out["ok"] is False
    assert "path" in (out.get("error") or "").lower()
