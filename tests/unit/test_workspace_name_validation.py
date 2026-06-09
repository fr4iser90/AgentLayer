"""Tests for workspace name validation and on-disk path containment."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.infrastructure.workspace_service import (
    WorkspaceCreateError,
    resolve_user_workspace_dir,
    validate_workspace_name,
)


class TestValidateWorkspaceName(unittest.TestCase):
    def test_accepts_normal_names(self) -> None:
        self.assertEqual(validate_workspace_name("  my-project  "), "my-project")
        self.assertEqual(validate_workspace_name("PIDEA"), "PIDEA")
        self.assertEqual(validate_workspace_name("repo-1.0"), "repo-1.0")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(WorkspaceCreateError):
            validate_workspace_name("")
        with self.assertRaises(WorkspaceCreateError):
            validate_workspace_name("   ")

    def test_rejects_path_segments(self) -> None:
        for bad in (".", "..", "a/b", "a\\b", "../escape", "foo/..", "foo\\bar"):
            with self.assertRaises(WorkspaceCreateError, msg=bad):
                validate_workspace_name(bad)

    def test_rejects_null_byte(self) -> None:
        with self.assertRaises(WorkspaceCreateError):
            validate_workspace_name("bad\u0000name")


class TestResolveUserWorkspaceDir(unittest.TestCase):
    def test_resolves_under_user_root(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            target = resolve_user_workspace_dir(base, "user-42", "my-repo")
            user_root = (base / "user-42").resolve()
            self.assertEqual(target, user_root / "my-repo")
            self.assertEqual(target.relative_to(user_root), Path("my-repo"))

    def test_rejects_traversal_name(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with self.assertRaises(WorkspaceCreateError):
                resolve_user_workspace_dir(base, "user-42", "..")


if __name__ == "__main__":
    unittest.main()
