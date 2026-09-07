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

    @mock.patch("apps.backend.domain.collections.projection.col_db.collection_metadata_patch")
    @mock.patch("apps.backend.domain.collections.projection.col_db.items_append")
    @mock.patch("apps.backend.domain.collections.projection.col_db.collection_ensure")
    @mock.patch("apps.backend.domain.collections.projection.col_db.collection_get")
    @mock.patch("apps.backend.domain.collections.projection.col_db.items_list")
    @mock.patch("apps.backend.domain.collections.projection.bindings_for_dashboard")
    def _project_with_legacy(
        self,
        collection_metadata: dict,
        mock_bindings: mock.MagicMock,
        mock_items: mock.MagicMock,
        mock_get: mock.MagicMock,
        mock_ensure: mock.MagicMock,
        mock_append: mock.MagicMock,
        mock_meta_patch: mock.MagicMock,
    ) -> tuple[dict, mock.MagicMock]:
        """Project an empty ``pets`` collection against a legacy payload that has rows."""
        mock_bindings.return_value = {"pets": "my-pets"}
        col = {"id": str(uuid.uuid4()), "slug": "my-pets", "metadata": collection_metadata}
        mock_get.return_value = col
        mock_ensure.return_value = col
        mock_items.return_value = []
        ui = {
            "version": 1,
            "blocks": [{"id": "t", "type": "table", "props": {"dataPath": "pets"}}],
        }
        data = project_dashboard_data(
            dashboard_id=uuid.uuid4(),
            owner_user_id=uuid.uuid4(),
            tenant_id=1,
            ui_layout=ui,
            view_bindings={},
            template_id="pets-v1",
            legacy_data={"pets": [{"id": "r_1", "name": "Kira"}]},
        )
        return data, mock_append

    def test_legacy_import_runs_once_for_a_fresh_collection(self) -> None:
        _data, mock_append = self._project_with_legacy({})
        mock_append.assert_called_once()

    def test_emptied_list_is_not_refilled_from_legacy_data(self) -> None:
        # The marker means the one-time migration already ran, so an empty list is intentional.
        _data, mock_append = self._project_with_legacy({"__legacy_import__pets": True})
        mock_append.assert_not_called()

    def test_internal_metadata_keys_are_not_projected(self) -> None:
        data, _append = self._project_with_legacy({"__legacy_import__pets": True, "notes": "hi"})
        self.assertEqual(data.get("notes"), "hi")
        self.assertNotIn("__legacy_import__pets", data)


if __name__ == "__main__":
    unittest.main()
