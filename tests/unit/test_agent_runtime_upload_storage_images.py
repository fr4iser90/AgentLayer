from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.application.agent_runtime.use_cases import upload_storage_images as mod


def test_storage_images_from_body_limits_and_normalizes() -> None:
    images = mod.storage_images_from_body(
        [
            {"name": " cat.png ", "dataUrl": "data:image/png;base64,aaa"},
            {"name": "", "data_url": "data:image/jpeg;base64,bbb"},
            {"name": "bad", "data_url": "https://example.test/image.png"},
            "ignored",
        ]
    )

    assert images == [
        {"name": "cat.png", "data_url": "data:image/png;base64,aaa"},
        {"name": "image_2.jpg", "data_url": "data:image/jpeg;base64,bbb"},
    ]


def test_dashboard_id_from_tool_result_accepts_nested_dashboard() -> None:
    did = str(uuid.uuid4())

    assert mod.dashboard_id_from_tool_result(f'{{"dashboard": {{"id": "{did}"}}}}') == did
    assert mod.dashboard_id_from_tool_result("not-json") is None


def test_upload_pending_storage_images_updates_context() -> None:
    uid = uuid.uuid4()
    did = uuid.uuid4()
    context = {
        "agent_storage_images_pending": [
            {"name": "a.png", "data_url": "data:image/png;base64,aaa"},
        ],
        "agent_storage_images_uploaded": 2,
    }

    with (
        patch.object(
            mod.dashboard_db,
            "dashboard_get",
            return_value={
                "ui_layout": {
                    "blocks": [
                        {"type": "gallery", "props": {"dataPath": "albums.0.photos"}},
                    ]
                }
            },
        ),
        patch.object(mod, "upload_dashboard_image", return_value={"ok": True}) as upload,
    ):
        result = mod.upload_pending_storage_images(
            tool_context=context,
            user_id=uid,
            tenant_id=1,
            dashboard_id=str(did),
        )

    assert result["ok"] is True
    assert result["uploaded"] == 1
    assert result["pending"] == 0
    assert context["agent_storage_images_pending"] == []
    assert context["agent_storage_images_uploaded"] == 3
    upload.assert_called_once_with(
        uid,
        1,
        did,
        base64_data="data:image/png;base64,aaa",
        original_name="a.png",
        append_list_path="albums.0.photos",
        caption="a.png",
    )
