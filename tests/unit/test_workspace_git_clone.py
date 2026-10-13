"""Tests for robust shallow git clone helper."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from apps.backend.infrastructure.workspace.workspace_git_clone import (
    GitCloneError,
    clone_shallow_repo,
    is_branch_missing_error,
    is_transient_git_error,
)


class TestGitErrorClassification(unittest.TestCase):
    def test_transient_curl56(self) -> None:
        msg = "error: RPC failed; curl 56 Recv failure: Connection reset by peer\nfatal: early EOF"
        self.assertTrue(is_transient_git_error(msg))

    def test_non_transient(self) -> None:
        self.assertFalse(is_transient_git_error("remote: Repository not found."))

    def test_branch_missing(self) -> None:
        self.assertTrue(
            is_branch_missing_error(
                "warning: Remote branch main not found in upstream origin\nfatal: ..."
            )
        )


class TestCloneShallowRepo(unittest.TestCase):
    def test_success_first_try(self) -> None:
        dest = Path("/tmp/ws-clone-ok")

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.shutil.which", return_value="/usr/bin/git"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.subprocess.run", side_effect=fake_run),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone._clean_dest"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.time.sleep"),
        ):
            clone_shallow_repo("https://github.com/org/repo.git", dest, branch="main", attempts=3)

    def test_retries_then_succeeds_with_http1(self) -> None:
        dest = Path("/tmp/ws-clone-retry")
        calls: list[dict] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            calls.append({"cmd": list(cmd), "env": kwargs.get("env") or {}})
            n = len(calls)
            if n == 1:
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr="error: RPC failed; curl 56 Recv failure: Connection reset by peer\nfatal: early EOF",
                )
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.shutil.which", return_value="/usr/bin/git"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.subprocess.run", side_effect=fake_run),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone._clean_dest"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.time.sleep") as sleep,
        ):
            clone_shallow_repo("https://github.com/org/repo.git", dest, branch="main", attempts=3)

        self.assertEqual(len(calls), 2)
        self.assertTrue(sleep.called)
        env2 = calls[1]["env"]
        self.assertEqual(env2.get("GIT_CONFIG_VALUE_0"), "HTTP/1.1")
        self.assertIn("--single-branch", calls[0]["cmd"])

    def test_exhausted_retries_raise(self) -> None:
        dest = Path("/tmp/ws-clone-fail")

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="curl 56 Recv failure: Connection reset by peer",
            )

        with (
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.shutil.which", return_value="/usr/bin/git"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.subprocess.run", side_effect=fake_run),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone._clean_dest"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.time.sleep"),
        ):
            with self.assertRaises(GitCloneError) as ctx:
                clone_shallow_repo("https://github.com/org/repo.git", dest, attempts=3)
        self.assertIn("Git clone failed", str(ctx.exception))
        self.assertEqual(ctx.exception.attempts, 3)

    def test_branch_missing_retries_without_branch(self) -> None:
        dest = Path("/tmp/ws-clone-branch")
        branches: list[str | None] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            cmd_l = list(cmd)
            if "--branch" in cmd_l:
                idx = cmd_l.index("--branch")
                branches.append(cmd_l[idx + 1])
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr="warning: Remote branch main not found in upstream origin",
                )
            branches.append(None)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with (
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.shutil.which", return_value="/usr/bin/git"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.subprocess.run", side_effect=fake_run),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone._clean_dest"),
            mock.patch("apps.backend.infrastructure.workspace.workspace_git_clone.time.sleep"),
        ):
            clone_shallow_repo("https://github.com/org/repo.git", dest, branch="main", attempts=3)

        self.assertEqual(branches[0], "main")
        self.assertIsNone(branches[1])


if __name__ == "__main__":
    unittest.main()
