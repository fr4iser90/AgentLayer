"""Tests for dashboard template export/import and block ref helpers."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure.dashboards.dashboard_template_ops import export_template_payload, validate_template_import


class TestTemplateOps(unittest.TestCase):
    def test_export_strips_agentlayer_keys(self) -> None:
        payload = export_template_payload(
            kind="custom",
            title="Test",
            ui_layout={"version": 1, "blocks": []},
            data={"items": [], "_agentlayer": {"x": 1}},
        )
        self.assertNotIn("_agentlayer", payload["initial_data"])
        self.assertEqual(payload["block_count"], 0)

    def test_validate_rejects_oversized_layout(self) -> None:
        blocks = [{"id": f"b{i}", "type": "markdown", "grid": {"x": 0, "y": i, "w": 6, "h": 4}, "props": {}} for i in range(65)]
        ul = {"version": 1, "blocks": blocks}
        _, _, err = validate_template_import(kind="custom", ui_layout=ul, data={})
        self.assertIn("exceeds", err or "")


if __name__ == "__main__":
    unittest.main()
