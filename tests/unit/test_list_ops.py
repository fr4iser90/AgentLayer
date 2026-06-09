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


def _dashboard_row(
    *,
    dashboard_id: uuid.UUID | None = None,
    data: dict | None = None,
    layout: dict | None = None,
) -> dict:
    return {
        "id": str(dashboard_id or uuid.uuid4()),
        "kind": "custom",
        "access_role": "owner",
        "access_scope": "full",
        "owner_user_id": str(uuid.uuid4()),
        "tenant_id": 1,
        "view_bindings": {},
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

    @patch("apps.backend.dashboard.list_ops.domain_svc.append_items")
    @patch("apps.backend.dashboard.list_ops.domain_svc.resolve_bindings_for_dashboard")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_append_writes_domain(self, mock_get, mock_bindings, mock_append) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        mock_get.return_value = _dashboard_row(data={"repos": []})
        mock_bindings.return_value = {"repos": "my-repos"}
        mock_append.return_value = {
            "ok": True,
            "source": "domain",
            "added_count": 1,
            "total_count": 1,
            "added": [{"id": "r_x", "title": "Alpha"}],
        }

        result = append_list_rows(
            uid,
            1,
            did,
            rows=[{"title": "Alpha", "remote_url": "https://github.com/a/b"}],
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("source"), "domain")
        mock_append.assert_called_once()

    @patch("apps.backend.dashboard.list_ops.domain_svc.delete_item")
    @patch("apps.backend.dashboard.list_ops.domain_svc.update_item")
    @patch("apps.backend.dashboard.list_ops.domain_svc.resolve_bindings_for_dashboard")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_update_and_delete_row(self, mock_get, mock_bindings, mock_update, mock_delete) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        row_id = "r_test123"
        mock_get.return_value = _dashboard_row(data={"repos": [{"id": row_id, "title": "Old"}]})
        mock_bindings.return_value = {"repos": "my-repos"}
        mock_update.return_value = {
            "ok": True,
            "source": "domain",
            "row": {"id": row_id, "title": "New"},
        }
        mock_delete.return_value = {
            "ok": True,
            "source": "domain",
            "collection_slug": "my-repos",
        }

        upd = update_list_row(uid, 1, did, row_id=row_id, patch={"title": "New"})
        self.assertTrue(upd.get("ok"))
        self.assertEqual(upd["row"]["title"], "New")

        with patch("apps.backend.domain.collections.db.collection_get") as mock_col:
            with patch("apps.backend.domain.collections.db.items_list") as mock_items:
                mock_col.return_value = {"id": str(uuid.uuid4())}
                mock_items.return_value = []
                deleted = delete_list_row(uid, 1, did, row_id=row_id)
        self.assertTrue(deleted.get("ok"))
        self.assertEqual(deleted.get("total_count"), 0)


class TestListAppendDedupeField(unittest.TestCase):
    @patch("apps.backend.dashboard.list_ops.domain_svc.resolve_bindings_for_dashboard")
    @patch("apps.backend.domain.collections.db.items_list")
    @patch("apps.backend.domain.collections.db.collection_get")
    @patch("apps.backend.dashboard.list_ops.dashboard_db.dashboard_get")
    def test_skips_duplicate_remote_url(
        self, mock_get, mock_col_get, mock_items_list, mock_bindings
    ) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        mock_get.return_value = _dashboard_row(
            dashboard_id=did,
            data={
                "repos": [
                    {"id": "r_existing", "remote_url": "https://github.com/org/existing.git"},
                ]
            },
        )
        mock_bindings.return_value = {"repos": "my-repos"}
        mock_col_get.return_value = {"id": str(uuid.uuid4())}
        mock_items_list.return_value = [
            {"id": "r_existing", "remote_url": "https://github.com/org/existing.git"},
        ]

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
