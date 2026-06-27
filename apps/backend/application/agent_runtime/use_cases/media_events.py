"""Agent runtime media events derived from tool results."""

from __future__ import annotations

import json
from typing import Any


def media_play_websocket_event(tool_name: str, result: str | None) -> dict[str, Any] | None:
    """When ``media_enqueue`` succeeded with ``play_now``, tell the Web UI to start the footer player."""
    if (tool_name or "").strip() != "media_enqueue" or not result:
        return None
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return None
    if payload.get("ok") is not True or not payload.get("now_playing_id"):
        return None
    item = payload.get("item")
    dash = payload.get("dashboard_id")
    qp = payload.get("queue_path")
    if not isinstance(item, dict) or not dash or not qp:
        return None
    queue = payload.get("queue")
    if not isinstance(queue, dict) or not isinstance(queue.get("items"), list):
        queue = {
            "now_playing_id": str(payload["now_playing_id"]),
            "items": [item],
            "shuffle": False,
            "repeat": "off",
        }
    return {
        "type": "agent.media_play",
        "dashboard_id": str(dash),
        "queue_path": str(qp),
        "now_playing_id": str(payload["now_playing_id"]),
        "item": item,
        "queue": queue,
    }
