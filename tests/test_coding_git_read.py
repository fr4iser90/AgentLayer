"""Tests for ``git_read`` (read-only git -C workspace)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from plugins.tools.integrations.github.git_read import git_read


def _have_git() -> bool:
    return shutil.which("git") is not None


@pytest.mark.skipif(not _have_git(), reason="git not installed")
def test_coding_git_read_operations(tmp_path: Path) -> None:
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
    (root / "hello.txt").write_text("world2\n", encoding="utf-8")

    ctx = {"workspace": {"path": str(root)}}

    for op in ("status", "branch", "log", "diff", "diff_stat"):
        out = git_read({"operation": op}, context=ctx)
        data = json.loads(out)
        assert data.get("ok") is True, (op, data)
        assert data.get("operation") == op
        assert "output" in data

    diff_file = git_read({"operation": "diff", "path": "hello.txt"}, context=ctx)
    d = json.loads(diff_file)
    assert d.get("ok") is True
    assert "hello.txt" in d.get("output", "")

    subprocess.run(
        ["git", "-C", str(root), "tag", "v0.1.0"],
        check=True,
        capture_output=True,
    )
    (root / "hello.txt").write_text("world3\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "hello.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "after tag"],
        check=True,
        capture_output=True,
    )
    ranged = git_read({"operation": "log", "since_ref": "v0.1.0", "max_commits": 10}, context=ctx)
    r = json.loads(ranged)
    assert r.get("ok") is True
    assert r.get("rev_range") == "v0.1.0..HEAD"
    assert "after tag" in r.get("output", "")


def test_coding_git_read_not_a_repo(tmp_path: Path) -> None:
    if not _have_git():
        pytest.skip("git not installed")
    ctx = {"workspace": {"path": str(tmp_path)}}
    out = git_read({"operation": "status"}, context=ctx)
    data = json.loads(out)
    assert data.get("ok") is False
    assert "git" in (data.get("error") or "").lower()


def test_coding_git_read_bad_path(tmp_path: Path) -> None:
    if not _have_git():
        pytest.skip("git not installed")
    root = tmp_path / "r2"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    ctx = {"workspace": {"path": str(root)}}
    out = git_read({"operation": "diff", "path": "../etc/passwd"}, context=ctx)
    data = json.loads(out)
    assert data.get("ok") is False
    assert "path" in (data.get("error") or "").lower()
