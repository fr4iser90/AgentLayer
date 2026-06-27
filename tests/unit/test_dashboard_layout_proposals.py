"""Tests for dashboard layout proposal store and apply."""

from __future__ import annotations

import unittest
import uuid

from apps.backend.infrastructure.dashboards.dashboard_layout_data_init import merge_data_for_layout
from apps.backend.infrastructure.dashboards.dashboard_layout_proposals import (
    get_latest_proposal_set,
    get_proposal_set,
    store_proposal_set,
)


class TestLayoutDataInit(unittest.TestCase):
    def test_merge_keeps_existing_and_adds_defaults(self) -> None:
        ul = {
            "version": 1,
            "blocks": [
                {
                    "id": "b1",
                    "type": "stat",
                    "grid": {"x": 0, "y": 0, "w": 4, "h": 3},
                    "props": {"dataPath": "stat_kpi"},
                },
                {
                    "id": "b2",
                    "type": "markdown",
                    "grid": {"x": 0, "y": 3, "w": 12, "h": 4},
                    "props": {"dataPath": "notes"},
                },
            ],
        }
        merged = merge_data_for_layout({"projects": [{"title": "A"}]}, ul)
        self.assertEqual(merged["projects"], [{"title": "A"}])
        self.assertIn("stat_kpi", merged)
        self.assertIn("notes", merged)


class TestLayoutProposalStore(unittest.TestCase):
    def test_store_and_get_latest(self) -> None:
        tid = 1
        uid = uuid.uuid4()
        did = uuid.uuid4()
        ul = {
            "version": 1,
            "blocks": [
                {
                    "id": "x1",
                    "type": "markdown",
                    "grid": {"x": 0, "y": 0, "w": 12, "h": 6},
                    "props": {"dataPath": "notes"},
                }
            ],
        }
        pset, err = store_proposal_set(
            tenant_id=tid,
            user_id=uid,
            dashboard_id=did,
            kind="custom",
            proposals=[
                {"title": "A", "summary": "First", "ui_layout": ul},
                {"title": "B", "summary": "Second", "ui_layout": ul},
            ],
        )
        self.assertIsNone(err)
        self.assertIsNotNone(pset)
        assert pset is not None
        latest = get_latest_proposal_set(tenant_id=tid, user_id=uid, dashboard_id=did)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.set_id, pset.set_id)
        loaded = get_proposal_set(
            tenant_id=tid,
            user_id=uid,
            dashboard_id=did,
            set_id=pset.set_id,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(len(loaded.proposals), 2)

    def test_rejects_invalid_layout(self) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        bad = {"version": 1, "blocks": "nope"}
        _, err = store_proposal_set(
            tenant_id=1,
            user_id=uid,
            dashboard_id=did,
            kind="custom",
            proposals=[{"title": "X", "ui_layout": bad}],
        )
        self.assertIsNotNone(err)


class TestNormalizeProposalUiLayout(unittest.TestCase):
    def test_array_wrapped_to_object(self) -> None:
        from plugins.tools.personal.dashboard.dashboard import _normalize_proposal_ui_layout

        blocks = [
            {
                "id": "h1",
                "type": "hero",
                "grid": {"x": 0, "y": 0, "w": 12, "h": 4},
                "props": {"title": "Hi"},
            }
        ]
        out = _normalize_proposal_ui_layout(blocks)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["version"], 1)
        self.assertEqual(out["blocks"], blocks)


if __name__ == "__main__":
    unittest.main()
