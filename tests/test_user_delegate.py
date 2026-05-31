"""User / Workspace Delegate config validation and merge."""

from __future__ import annotations

import unittest

from apps.backend.domain.delegate_config_schema import (
    default_delegate_config,
    normalize_delegate_config,
)
from apps.backend.domain.delegate_merge import build_delegate_context_block, merge_delegate_configs


class TestDelegateConfigSchema(unittest.TestCase):
    def test_default_roundtrip(self) -> None:
        d = default_delegate_config()
        out = normalize_delegate_config(d, scope="user")
        self.assertEqual(out["communication"]["directness"], "medium")
        self.assertTrue(out["engineering"]["security_first"])
        self.assertEqual(out["decisioning"]["risk_tolerance"], "low")
        self.assertTrue(out["escalation"]["ask_on_production_changes"])
        self.assertEqual(out["engineering"]["primary_goal"], "stability")

    def test_workspace_default_risk_medium(self) -> None:
        out = default_delegate_config(scope="workspace")
        self.assertEqual(out["decisioning"]["risk_tolerance"], "medium")

    def test_invalid_level_falls_back(self) -> None:
        raw = default_delegate_config()
        raw["communication"]["directness"] = "banana"
        out = normalize_delegate_config(raw, scope="user")
        self.assertEqual(out["communication"]["directness"], "medium")

    def test_goals_from_lines(self) -> None:
        raw = default_delegate_config()
        raw["goals"] = ["a", "", "b"]
        out = normalize_delegate_config(raw, scope="user")
        self.assertEqual(out["goals"], ["a", "b"])

    def test_workspace_size_cap(self) -> None:
        raw = default_delegate_config()
        raw["goals"] = ["x" * 500] * 20
        with self.assertRaises(ValueError):
            normalize_delegate_config(raw, scope="workspace")


class TestDelegateMerge(unittest.TestCase):
    def test_workspace_overrides_engineering(self) -> None:
        user = default_delegate_config()
        user["engineering"]["prefer_tests"] = False
        ws = default_delegate_config()
        ws["engineering"]["prefer_tests"] = True
        merged = merge_delegate_configs(user, ws)
        self.assertTrue(merged["engineering"]["prefer_tests"])

    def test_workspace_goals_replace_when_non_empty(self) -> None:
        user = default_delegate_config()
        user["goals"] = ["global goal"]
        ws = default_delegate_config()
        ws["goals"] = ["project goal"]
        merged = merge_delegate_configs(user, ws)
        self.assertEqual(merged["goals"], ["project goal"])

    def test_context_block_contains_goals(self) -> None:
        cfg = default_delegate_config()
        cfg["goals"] = ["fix security on main"]
        block = build_delegate_context_block(user_config=cfg, workspace_label="demo")
        self.assertIn("Stellvertreter", block)
        self.assertIn("fix security on main", block)
        self.assertIn("demo", block)
        self.assertIn("risk_tolerance=low", block)
        self.assertIn("primary_goal=stability", block)

    def test_workspace_priorities_replace(self) -> None:
        user = default_delegate_config()
        ws = default_delegate_config(scope="workspace")
        ws["engineering"]["priorities"] = ["speed", "security"]
        merged = merge_delegate_configs(user, ws)
        self.assertEqual(merged["engineering"]["priorities"], ["speed", "security"])


if __name__ == "__main__":
    unittest.main()
