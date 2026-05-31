"""Shared helpers for friend-scoped tools (lookup, calendar secrets, share labels)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure.db import db

CALENDAR_SECRET_KEYS: tuple[str, ...] = ("google_calendar", "calendar_ics")

RESOURCE_TYPE_LABELS: dict[str, str] = {
    "google_calendar": "Google Calendar",
    "github_activity": "GitHub Activity",
    "todoist": "Todoist",
    "notes": "Notes",
    "roadmap": "Project Roadmap",
    # Legacy alias stored before UI used google_calendar.
    "calendar": "Google Calendar",
}


def resource_type_label(resource_type: str) -> str:
    key = (resource_type or "").strip().lower()
    return RESOURCE_TYPE_LABELS.get(key, key or "unknown")


def resolve_friend_by_name(user_id: uuid.UUID, name_query: str) -> dict[str, Any] | None:
    from apps.backend.infrastructure.db.friends_db import friends_list

    search_name = (name_query or "").strip().lower()
    if not search_name:
        return None
    for friend in friends_list(user_id):
        name = friend.get("display_name", "").lower()
        email = friend.get("email", "").lower()
        if search_name in name or search_name in email:
            return friend
    return None


def _parse_calendar_secret(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    url = str(obj.get("ics_url") or obj.get("url") or "").strip()
    return url or None


def friend_calendar_ics_url(friend_user_id: uuid.UUID) -> str | None:
    for service_key in CALENDAR_SECRET_KEYS:
        raw = db.user_secret_get_plaintext(friend_user_id, service_key)
        url = _parse_calendar_secret(raw)
        if url:
            return url
    return None
