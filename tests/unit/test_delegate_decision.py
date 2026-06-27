"""Tests for delegate decision autonomy guards."""

from __future__ import annotations

import unittest

from apps.backend.domain.delegation.decision import _autonomy_blocks_action
from apps.backend.domain.delegation.config_schema import default_delegate_config


class TestDelegateDecision(unittest.TestCase):
    def test_blocks_merge_when_autonomy_denies(self) -> None:
        cfg = default_delegate_config()
        cfg["autonomy"]["can_merge_prs"] = False
        blocked, reason = _autonomy_blocks_action(cfg, "Please merge pull request #42")
        self.assertTrue(blocked)
        self.assertIn("can_merge_prs", reason)

    def test_allows_neutral_message(self) -> None:
        cfg = default_delegate_config()
        blocked, _ = _autonomy_blocks_action(cfg, "Run unit tests and fix failures")
        self.assertFalse(blocked)


if __name__ == "__main__":
    unittest.main()
