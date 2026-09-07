"""Tests for ``safe_resolve_under_workspace`` (workspace HTTP browse)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.api.workspaces.controllers.workspaces_api import safe_resolve_under_workspace


class TestSafeResolveUnderWorkspace(unittest.TestCase):
    def test_root_and_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a" / "b").mkdir(parents=True)
            self.assertEqual(safe_resolve_under_workspace(root, None), root.resolve())
            self.assertEqual(safe_resolve_under_workspace(root, ""), root.resolve())
            self.assertEqual(safe_resolve_under_workspace(root, "a/b"), (root / "a" / "b").resolve())

    def test_rejects_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                safe_resolve_under_workspace(root, "/etc/passwd")

    def test_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                safe_resolve_under_workspace(root, "../outside")


if __name__ == "__main__":
    unittest.main()
