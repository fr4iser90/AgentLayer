"""Domain collections — source of truth tests."""

from __future__ import annotations

import unittest
import uuid
from unittest import mock

from apps.backend.domain.collections.bindings import (
    default_collection_slug_for_path,
    parse_view_bindings,
)
from apps.backend.domain.collections import db as col_db
from apps.backend.domain.collections.projection import project_dashboard_data


class TestBindings(unittest.TestCase):
    def test_parse_view_bindings(self) -> None:
        raw = {"pets": "my-pets", "notes": {"collection_slug": "my-pets"}}
        out = parse_view_bindings(raw)
        self.assertEqual(out["pets"], "my-pets")
        self.assertEqual(out["notes"], "my-pets")

    def test_default_slug(self) -> None:
        self.assertEqual(default_collection_slug_for_path("albums.0.photos"), "albums.0.photos")


class TestCollectionRow(unittest.TestCase):
    def test_collection_row_from_ensure_shape(self) -> None:
        uid = uuid.uuid4()
        row = {
            "id": uuid.uuid4(),
            "tenant_id": 1,
            "owner_user_id": uid,
            "slug": "my-pets",
            "title": "my-pets",
            "schema_hint": None,
            "metadata": {},
            "created_at": None,
            "updated_at": None,
        }
        out = col_db._collection_row(row)
        self.assertEqual(out["tenant_id"], 1)
        self.assertEqual(out["owner_user_id"], str(uid))
        self.assertEqual(out["slug"], "my-pets")


class TestProjection(unittest.TestCase):
    @mock.patch("apps.backend.domain.collections.projection.col_db.collection_get")
    @mock.patch("apps.backend.domain.collections.projection.col_db.items_list")
    @mock.patch("apps.backend.domain.collections.projection.bindings_for_dashboard")
    def test_project_list_path(
        self,
        mock_bindings: mock.MagicMock,
        mock_items: mock.MagicMock,
        mock_get: mock.MagicMock,
    ) -> None:
        did = uuid.uuid4()
        uid = uuid.uuid4()
        mock_bindings.return_value = {"pets": "my-pets"}
        mock_get.return_value = {
            "id": str(uuid.uuid4()),
            "metadata": {"notes": "hello"},
        }
        mock_items.return_value = [{"id": "r_1", "name": "Kira"}]

        ui = {
            "version": 1,
            "blocks": [
                {
                    "id": "t",
                    "type": "table",
                    "props": {"dataPath": "pets"},
                }
            ],
        }
        data = project_dashboard_data(
            dashboard_id=did,
            owner_user_id=uid,
            tenant_id=1,
            ui_layout=ui,
            view_bindings={},
            template_id="pets-v1",
            legacy_data=None,
        )
        self.assertEqual(data.get("pets"), [{"id": "r_1", "name": "Kira"}])
        self.assertEqual(data.get("notes"), "hello")


if __name__ == "__main__":
    unittest.main()
