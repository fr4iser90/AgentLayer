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


def _ws(*, did: uuid.UUID, layout: dict) -> dict:
    return {
        "id": str(did),
        "kind": "custom",
        "template_id": None,
        "access_role": "owner",
        "access_scope": "full",
        "owner_user_id": str(uuid.uuid4()),
        "tenant_id": 1,
        "view_bindings": {},
        "data": {"repos": [], "events": []},
        "ui_layout": layout,
    }


class TestMegaBoardGeneric(unittest.TestCase):
    @patch("apps.backend.dashboard.list_ops.domain_svc.append_items")
    @patch("apps.backend.dashboard.list_ops.domain_svc.resolve_bindings_for_dashboard")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_custom_board_two_lists_and_compute(
        self, mock_get, mock_bindings, mock_append
    ) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        layout = _mega_layout()
        mock_get.return_value = _ws(did=did, layout=layout)
        mock_bindings.return_value = {"repos": "repos", "events": "events"}

        repos: list[dict] = []
        events: list[dict] = []

        def _append(**kwargs: object) -> dict:
            path = str(kwargs.get("list_path") or "")
            rows = kwargs.get("rows") or []
            if path == "repos":
                repos.extend(rows)  # type: ignore[arg-type]
                return {
                    "ok": True,
                    "source": "domain",
                    "added_count": len(rows),  # type: ignore[arg-type]
                    "total_count": len(repos),
                }
            if path == "events":
                events.extend(rows)  # type: ignore[arg-type]
                return {
                    "ok": True,
                    "source": "domain",
                    "added_count": len(rows),  # type: ignore[arg-type]
                    "total_count": len(events),
                }
            return {"ok": False, "error": "unknown path"}

        mock_append.side_effect = _append

        r1 = append_list_rows(
            uid,
            1,
            did,
            list_path="repos",
            rows=[{"title": "app-a", "remote_url": "https://github.com/o/a"}],
        )
        self.assertTrue(r1.get("ok"))
        self.assertEqual(r1.get("source"), "domain")
        self.assertEqual(len(repos), 1)

        r2 = append_list_rows(
            uid,
            1,
            did,
            list_path="events",
            rows=[{"title": "Launch", "status": "open"}, {"title": "Done thing", "status": "done"}],
        )
        self.assertTrue(r2.get("ok"))
        self.assertEqual(len(events), 2)

        finalized = finalize_dashboard_data({"repos": repos, "events": events}, layout)
        self.assertEqual(finalized["stat_repos"]["value"], "1")
        self.assertEqual(finalized["stat_events_open"]["value"], "1")


if __name__ == "__main__":
    unittest.main()
