"""Tests for media quota/gate structured responses."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from plugins.tools.personal.media import media as media_tools


def test_media_quota_when_library_disabled() -> None:
    uid = uuid.uuid4()
    with patch.object(media_tools, "get_identity", return_value=(1, uid)):
        with patch.object(media_tools.media_db, "media_tables_exist", return_value=True):
            with patch.object(
                media_tools.media_policy,
                "media_quota_snapshot",
                return_value={
                    "library_enabled": False,
                    "sharing_enabled": False,
                    "used_bytes": 0,
                    "quota_bytes": 1000,
                    "remaining_bytes": 1000,
                },
            ):
                with patch.object(
                    media_tools.media_policy,
                    "effective_media_upload_enabled",
                    return_value=False,
                ):
                    out = json.loads(media_tools.quota({}))
    assert out["ok"] is True
    assert out["library_enabled"] is False


def test_media_gate_structured_when_disabled() -> None:
    uid = uuid.uuid4()
    with patch.object(media_tools.media_db, "media_tables_exist", return_value=True):
        with patch.object(
            media_tools.media_policy,
            "effective_media_library_enabled",
            return_value=False,
        ):
            blocked = media_tools._media_gate(uid)
    assert blocked is not None
    data = json.loads(blocked)
    assert data == {
        "ok": False,
        "error": "media library disabled by operator",
        "library_enabled": False,
    }
