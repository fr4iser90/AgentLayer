"""Tests for UX metadata merged into tools_meta."""

from __future__ import annotations

import types
import unittest

from apps.backend.domain.plugin_system.tool_ui_catalog import apply_tool_ui_metadata


class TestToolUiCatalog(unittest.TestCase):
    def test_defaults_by_tool_id(self) -> None:
        mod = types.SimpleNamespace(
            TOOL_LABEL="",
            TOOL_DESCRIPTION="Desc here",
        )
        entry: dict = {"id": "gmail", "domain": "gmail", "tools": ["a"]}
        apply_tool_ui_metadata(mod, entry)
        ui = entry.get("ui")
        self.assertIsInstance(ui, dict)
        assert ui is not None
        self.assertEqual(ui.get("category"), "productivity")
        self.assertEqual(ui.get("display_name"), "Gmail")
        self.assertEqual(ui.get("icon"), "mail")
        self.assertIn("tagline", ui)

    def test_tool_ui_overrides(self) -> None:
        mod = types.SimpleNamespace(
            TOOL_UI={"display_name": "GH", "category": "developer", "order": 3},
            TOOL_LABEL="ignored",
            TOOL_DESCRIPTION="",
        )
        entry: dict = {"id": "github", "domain": "github", "tools": ["x"]}
        apply_tool_ui_metadata(mod, entry)
        ui = entry["ui"]
        self.assertEqual(ui.get("display_name"), "GH")
        self.assertEqual(ui.get("order"), 3)

    def test_unknown_package_falls_back_system(self) -> None:
        mod = types.SimpleNamespace(TOOL_LABEL="My Lab", TOOL_DESCRIPTION="")
        entry: dict = {"id": "totally_unknown_xyz", "domain": "unknown_domain", "tools": ["z"]}
        apply_tool_ui_metadata(mod, entry)
        ui = entry["ui"]
        self.assertEqual(ui.get("category"), "system")
        self.assertEqual(ui.get("display_name"), "My Lab")


if __name__ == "__main__":
    unittest.main()
