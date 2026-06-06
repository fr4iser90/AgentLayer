"""Generic mega-board: two lists + compute KPIs without domain-specific backend code."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from apps.backend.dashboard.data_compute import finalize_dashboard_data
from apps.backend.dashboard.list_ops import append_list_rows


def _mega_layout() -> dict:
    return {
        "version": 2,
        "blocks": [
            {
                "id": "repos-grid",
                "type": "card_grid",
                "grid": {"x": 0, "y": 0, "w": 8, "h": 8},
                "props": {"dataPath": "repos", "title": "Repos"},
            },
            {
                "id": "events-table",
                "type": "table",
                "grid": {"x": 8, "y": 0, "w": 4, "h": 8},
                "props": {"dataPath": "events", "columns": []},
            },
            {
                "id": "kpi-repos",
                "type": "stat",
                "grid": {"x": 0, "y": 8, "w": 3, "h": 3},
                "props": {
                    "dataPath": "stat_repos",
                    "title": "Repos",
                    "compute": {"op": "count", "from": "repos"},
                },
            },
            {
                "id": "kpi-events-open",
                "type": "stat",
                "grid": {"x": 3, "y": 8, "w": 3, "h": 3},
                "props": {
                    "dataPath": "stat_events_open",
                    "title": "Open events",
                    "compute": {
                        "op": "count_where",
                        "from": "events",
                        "where": [{"field": "status", "neq": "done"}],
                    },
                },
            },
        ],
    }


class TestMegaBoardGeneric(unittest.TestCase):
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_update")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_custom_board_two_lists_and_compute(self, mock_get, mock_update) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        layout = _mega_layout()
        mock_get.return_value = {
            "kind": "custom",
            "template_id": None,
            "access_role": "owner",
            "access_scope": "full",
            "data": {"repos": [], "events": [], "stat_repos": {"value": 0}, "stat_events_open": {"value": 0}},
            "ui_layout": layout,
        }
        mock_update.return_value = {"id": str(did)}

        r1 = append_list_rows(
            uid,
            1,
            did,
            list_path="repos",
            rows=[{"title": "app-a", "remote_url": "https://github.com/o/a"}],
        )
        self.assertTrue(r1.get("ok"))

        saved = mock_update.call_args.kwargs["data"]
        self.assertEqual(len(saved["repos"]), 1)

        mock_get.return_value = {
            **mock_get.return_value,
            "data": saved,
        }
        r2 = append_list_rows(
            uid,
            1,
            did,
            list_path="events",
            rows=[{"title": "Launch", "status": "open"}, {"title": "Done thing", "status": "done"}],
        )
        self.assertTrue(r2.get("ok"))
        saved2 = mock_update.call_args.kwargs["data"]
        self.assertEqual(saved2["stat_repos"]["value"], "1")
        self.assertEqual(saved2["stat_events_open"]["value"], "1")

        finalized = finalize_dashboard_data(
            {"repos": saved2["repos"], "events": saved2["events"]},
            layout,
        )
        self.assertEqual(finalized["stat_repos"]["value"], "1")
        self.assertEqual(finalized["stat_events_open"]["value"], "1")


if __name__ == "__main__":
    unittest.main()
