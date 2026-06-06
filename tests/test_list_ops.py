"""Tests for generic dashboard list row CRUD."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from apps.backend.dashboard.list_ops import (
    append_list_rows,
    delete_list_row,
    resolve_list_path,
    update_list_row,
)


def _dashboard_row(*, data: dict | None = None, layout: dict | None = None) -> dict:
    return {
        "kind": "custom",
        "access_role": "owner",
        "access_scope": "full",
        "data": data or {},
        "ui_layout": layout
        or {
            "version": 2,
            "blocks": [
                {
                    "id": "tbl-1",
                    "type": "table",
                    "grid": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "props": {"dataPath": "repos", "columns": []},
                },
                {
                    "id": "kpi",
                    "type": "stat",
                    "grid": {"x": 0, "y": 8, "w": 3, "h": 3},
                    "props": {
                        "dataPath": "stat_total",
                        "title": "Total",
                        "compute": {"op": "count", "from": "repos"},
                    },
                },
            ],
        },
    }


class TestListOps(unittest.TestCase):
    def test_resolve_list_path_from_layout(self) -> None:
        ws = _dashboard_row()
        self.assertEqual(resolve_list_path(ws, None), "repos")
        self.assertEqual(resolve_list_path(ws, "events"), "events")

    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_update")
    def test_append_recomputes_stats(self, mock_update, mock_get) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        mock_get.return_value = _dashboard_row(data={"repos": [], "stat_total": {"value": 0}})
        mock_update.return_value = {"id": str(did)}

        result = append_list_rows(
            uid,
            1,
            did,
            rows=[{"title": "Alpha", "remote_url": "https://github.com/a/b"}],
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("added_count"), 1)
        saved = mock_update.call_args.kwargs.get("data") or mock_update.call_args[0][3]
        if isinstance(mock_update.call_args, tuple):
            saved = mock_update.call_args[0][3] if len(mock_update.call_args[0]) > 3 else saved
        # dashboard_update(user_id, tenant_id, dashboard_id, data=...)
        saved = mock_update.call_args.kwargs["data"]
        self.assertEqual(len(saved["repos"]), 1)
        self.assertEqual(saved["stat_total"]["value"], "1")

    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_update")
    def test_update_and_delete_row(self, mock_update, mock_get) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        row_id = "r_test123"
        mock_get.return_value = _dashboard_row(
            data={
                "repos": [{"id": row_id, "title": "Old"}],
                "stat_total": {"value": 1},
            }
        )
        mock_update.return_value = {"id": str(did)}

        upd = update_list_row(uid, 1, did, row_id=row_id, patch={"title": "New"})
        self.assertTrue(upd.get("ok"))
        self.assertEqual(upd["row"]["title"], "New")

        mock_get.return_value = _dashboard_row(data={"repos": [{"id": row_id, "title": "New"}]})
        deleted = delete_list_row(uid, 1, did, row_id=row_id)
        self.assertTrue(deleted.get("ok"))
        self.assertEqual(deleted.get("total_count"), 0)


class TestListAppendDedupeField(unittest.TestCase):
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_update")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_skips_duplicate_remote_url(self, mock_get, mock_update) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        mock_get.return_value = _dashboard_row(
            data={
                "repos": [
                    {"id": "r_existing", "remote_url": "https://github.com/org/existing.git"},
                ]
            }
        )
        mock_update.return_value = {"id": str(did)}

        result = append_list_rows(
            uid,
            1,
            did,
            list_path="repos",
            rows=[{"remote_url": "https://github.com/org/existing.git", "title": "Dup"}],
            dedupe_field="remote_url",
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("skipped_count"), 1)


if __name__ == "__main__":
    unittest.main()
