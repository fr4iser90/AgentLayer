"""Tests for chat → footer mini-player websocket event."""

from __future__ import annotations

import json

from apps.backend.application.agent_runtime.runtime.io import media_play_websocket_event


def test_media_play_event_from_enqueue_with_play_now() -> None:
    result = json.dumps(
        {
            "ok": True,
            "dashboard_id": "9c90b43b-3544-47b2-8381-2e34ca1d4abb",
            "queue_path": "sections.main.queue",
            "now_playing_id": "f61060dc-0c30-4648-a8d4-57aa5655d36d",
            "item": {
                "ref": "media:f61060dc-0c30-4648-a8d4-57aa5655d36d",
                "source_kind": "external_link",
                "external_url": "https://example.com/stream.mp3",
            },
            "queue": {
                "now_playing_id": "f61060dc-0c30-4648-a8d4-57aa5655d36d",
                "items": [
                    {
                        "ref": "media:f61060dc-0c30-4648-a8d4-57aa5655d36d",
                        "source_kind": "external_link",
                        "external_url": "https://example.com/stream.mp3",
                    }
                ],
                "shuffle": False,
                "repeat": "off",
            },
        }
    )
    ev = media_play_websocket_event("media_enqueue", result)
    assert ev is not None
    assert ev["type"] == "agent.media_play"
    assert ev["dashboard_id"] == "9c90b43b-3544-47b2-8381-2e34ca1d4abb"
    assert ev["queue_path"] == "sections.main.queue"


def test_media_play_event_skipped_without_now_playing() -> None:
    result = json.dumps({"ok": True, "dashboard_id": "x", "queue_path": "media_queue", "item": {}})
    assert media_play_websocket_event("media_enqueue", result) is None


def test_media_play_event_synthesizes_queue_from_item() -> None:
    result = json.dumps(
        {
            "ok": True,
            "dashboard_id": "9c90b43b-3544-47b2-8381-2e34ca1d4abb",
            "queue_path": "media_queue",
            "now_playing_id": "abc",
            "item": {"ref": "media:abc", "source_kind": "external_link", "external_url": "https://x/a.mp3"},
        }
    )
    ev = media_play_websocket_event("media_enqueue", result)
    assert ev is not None
    assert ev["queue"]["items"][0]["ref"] == "media:abc"
