"""Unit tests for implementation-branch slug helper (git branch API uses it)."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure.workspace import workspace_service as ws_svc


class TestImplementationBranchSlug(unittest.TestCase):
    def test_sanitize_empty_falls_back_to_hex(self) -> None:
        s = ws_svc._sanitize_implementation_branch_slug("")
        self.assertEqual(len(s), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in s))

    def test_sanitize_strips_unsafe_chars(self) -> None:
        s = ws_svc._sanitize_implementation_branch_slug("my run id!!!")
        self.assertEqual(s, "my-run-id")

    def test_sanitize_truncates(self) -> None:
        long = "a" * 80
        s = ws_svc._sanitize_implementation_branch_slug(long)
        self.assertLessEqual(len(s), 40)


if __name__ == "__main__":
    unittest.main()
