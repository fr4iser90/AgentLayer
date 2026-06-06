"""Unit tests for media agent tool helpers."""

from __future__ import annotations

from plugins.tools.personal.media import media as media_tools


def test_read_queue_defaults() -> None:
    q = media_tools._read_queue(None)
    assert q["items"] == []
    assert q["now_playing_id"] is None
    assert q["repeat"] == "off"


def test_read_queue_parses_items() -> None:
    raw = {"now_playing_id": "abc", "items": [{"ref": "media:abc"}], "repeat": "all"}
    q = media_tools._read_queue(raw)
    assert q["now_playing_id"] == "abc"
    assert len(q["items"]) == 1
    assert q["repeat"] == "all"


def test_media_queue_paths_from_layout() -> None:
    ws = {
        "ui_layout": {
            "version": 1,
            "blocks": [
                {
                    "id": "b1",
                    "type": "media_player",
                    "props": {"dataPath": "station_queue"},
                },
                {"id": "b2", "type": "table", "props": {"dataPath": "items"}},
            ],
        }
    }
    assert media_tools._media_queue_paths(ws) == ["station_queue"]


def test_media_queue_paths_fallback() -> None:
    ws = {"ui_layout": {"version": 1, "blocks": []}}
    assert media_tools._media_queue_paths(ws) == ["media_queue"]


def test_queue_item_from_upload_row() -> None:
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "source_kind": "upload",
        "title": "Track",
        "artist": "Artist",
    }
    item = media_tools._queue_item_from_media_row(row)
    assert item["ref"] == "media:11111111-1111-1111-1111-111111111111"
    assert item["stream_url"].endswith("/stream")
    assert item["title"] == "Track"
