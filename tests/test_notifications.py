"""Unit tests for in-app notifications."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure.notifications_delivery import should_deliver_external
from apps.backend.infrastructure.notifications_service import infer_block_ids_from_patches


class TestNotificationBlockInference(unittest.TestCase):
    def test_maps_data_path_to_block_id(self) -> None:
        ui = {
            "blocks": [
                {"id": "blk_stats", "type": "stat", "props": {"dataPath": "stat_projects"}},
                {"id": "blk_table", "type": "table", "props": {"dataPath": "projects"}},
            ]
        }
        patches = [{"path": "projects.0.title", "value": "x"}]
        self.assertEqual(infer_block_ids_from_patches(patches, ui), ["blk_table"])

    def test_multiple_blocks(self) -> None:
        ui = {
            "blocks": [
                {"id": "a", "type": "stat", "props": {"dataPath": "stat_linked"}},
                {"id": "b", "type": "stat", "props": {"dataPath": "stat_projects"}},
            ]
        }
        patches = [{"path": "stat_linked", "value": {"value": "1"}}]
        self.assertEqual(infer_block_ids_from_patches(patches, ui), ["a"])

    def test_empty_when_no_match(self) -> None:
        ui = {"blocks": [{"id": "x", "type": "markdown", "props": {"dataPath": "notes"}}]}
        patches = [{"path": "other", "value": 1}]
        self.assertEqual(infer_block_ids_from_patches(patches, ui), [])

    def test_nested_section_block(self) -> None:
        ui = {
            "blocks": [
                {
                    "id": "sec1",
                    "type": "section",
                    "props": {
                        "nested": {
                            "version": 2,
                            "blocks": [
                                {
                                    "id": "nested_kpi",
                                    "type": "stat",
                                    "props": {"dataPath": "stat_projects"},
                                }
                            ],
                        }
                    },
                }
            ]
        }
        patches = [{"path": "stat_projects.value", "value": "3"}]
        self.assertEqual(infer_block_ids_from_patches(patches, ui), ["nested_kpi"])


class TestExternalDeliveryPolicy(unittest.TestCase):
    def _prefs(self, **kw: bool) -> dict:
        base = {
            "telegram_enabled": True,
            "discord_enabled": False,
            "telegram_schedules": True,
            "telegram_dashboard": False,
            "discord_schedules": True,
            "discord_dashboard": False,
            "external_failures_only": True,
        }
        base.update(kw)
        return base

    def test_failures_only_blocks_success(self) -> None:
        n = {"kind": "scheduler_job_done", "severity": "info"}
        self.assertFalse(
            should_deliver_external(prefs=self._prefs(), channel="telegram", notification=n)
        )

    def test_failures_always_sent(self) -> None:
        n = {"kind": "scheduler_job_failed", "severity": "warning"}
        self.assertTrue(
            should_deliver_external(prefs=self._prefs(), channel="telegram", notification=n)
        )

    def test_dashboard_requires_opt_in(self) -> None:
        n = {"kind": "dashboard_agent_update", "severity": "info"}
        self.assertFalse(
            should_deliver_external(prefs=self._prefs(), channel="telegram", notification=n)
        )
        self.assertTrue(
            should_deliver_external(
                prefs=self._prefs(telegram_dashboard=True, external_failures_only=False),
                channel="telegram",
                notification=n,
            )
        )


if __name__ == "__main__":
    unittest.main()
