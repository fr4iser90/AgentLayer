"""Tests for dashboard.upload_file and file_upload helpers."""

from __future__ import annotations

import base64
import json
import unittest
import uuid
from unittest import mock

from apps.backend.infrastructure.dashboards.dashboard_file_upload import (
    decode_image_base64,
    store_dashboard_image,
    upload_dashboard_image,
)


# Minimal valid 1x1 PNG
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestDecodeImageBase64(unittest.TestCase):
    def test_raw_base64(self) -> None:
        data, err = decode_image_base64(base64.b64encode(_TINY_PNG).decode())
        self.assertIsNone(err)
        assert data is not None
        self.assertEqual(data, _TINY_PNG)

    def test_data_url(self) -> None:
        data_url = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()
        data, err = decode_image_base64(data_url)
        self.assertIsNone(err)
        assert data is not None
        self.assertEqual(len(data), len(_TINY_PNG))


class TestUploadFileTool(unittest.TestCase):
    @mock.patch("plugins.tools.personal.dashboard.dashboard.upload_dashboard_image")
    @mock.patch("plugins.tools.personal.dashboard.dashboard.resolve_dashboard_id")
    @mock.patch("plugins.tools.personal.dashboard.dashboard.get_identity")
    def test_upload_file_returns_gallery_ref(
        self,
        mock_ident: mock.MagicMock,
        mock_resolve: mock.MagicMock,
        mock_upload: mock.MagicMock,
    ) -> None:
        from plugins.tools.personal.dashboard.dashboard import upload_file

        wid = uuid.uuid4()
        mock_ident.return_value = (1, uuid.uuid4())
        mock_resolve.return_value = (wid, None)
        mock_upload.return_value = {
            "ok": True,
            "dashboard_id": str(wid),
            "gallery_ref": "file:abc-123",
        }

        out = json.loads(
            upload_file(
                {
                    "base64_data": base64.b64encode(_TINY_PNG).decode(),
                    "append_list_path": "albums.0.photos",
                    "caption": "Kira",
                }
            )
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["gallery_ref"], "file:abc-123")
        mock_upload.assert_called_once()


class TestStoreDashboardImage(unittest.TestCase):
    @mock.patch("apps.backend.infrastructure.dashboards.dashboard_file_upload.col_db.attachment_insert")
    @mock.patch("apps.backend.infrastructure.dashboards.dashboard_file_upload.domain_svc.resolve_bindings_for_dashboard")
    @mock.patch("apps.backend.infrastructure.dashboards.dashboard_file_upload.file_storage.write_bytes")
    @mock.patch("apps.backend.infrastructure.dashboards.dashboard_file_upload.dashboard_db.dashboard_get")
    def test_store_ok(
        self,
        mock_get: mock.MagicMock,
        mock_write: mock.MagicMock,
        mock_bindings: mock.MagicMock,
        mock_att: mock.MagicMock,
    ) -> None:
        uid = uuid.uuid4()
        did = uuid.uuid4()
        mock_get.return_value = {
            "id": str(did),
            "owner_user_id": str(uid),
            "tenant_id": 1,
            "access_role": "owner",
            "access_scope": "full",
            "ui_layout": {"version": 1, "blocks": []},
            "view_bindings": {},
        }
        mock_bindings.return_value = {}
        mock_att.return_value = {
            "id": str(uuid.uuid4()),
            "gallery_ref": "file:abc",
            "content_type": "image/png",
            "size_bytes": len(_TINY_PNG),
            "original_name": "x.png",
        }

        with mock.patch(
            "apps.backend.domain.shares.dashboard_grant.dashboard_tenant_id",
            return_value=1,
        ):
            out = store_dashboard_image(uid, 1, did, _TINY_PNG)
        self.assertTrue(out["ok"])
        self.assertTrue(str(out.get("gallery_ref", "")).startswith("file:"))


if __name__ == "__main__":
    unittest.main()
