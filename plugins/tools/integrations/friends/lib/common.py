"""Shared helpers for friend-scoped tools (lookup, calendar secrets, share labels)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure.db import db

CALENDAR_SECRET_KEYS: tuple[str, ...] = ("google_calendar", "calendar_ics")

def resource_type_label(resource_type: str, *, lang: str = "en") -> str:
    from apps.backend.domain.shares.catalog import resource_type_label as _catalog_label

    return _catalog_label(resource_type, lang=lang)


def resolve_message_recipient(user_id: uuid.UUID, name_or_email: str) -> dict[str, Any] | None:
    """Resolve a friend or known contact to AgentLayer user id and channel ids."""
    raw = (name_or_email or "").strip()
    if not raw:
        return None

    from apps.backend.infrastructure.db.friends_db import friends_list

    search = raw.lower()
    if "@" in search:
        for friend in friends_list(user_id):
            if search == str(friend.get("email") or "").lower():
                fid = friend.get("friend_user_id")
                if fid:
                    return _recipient_from_user_uuid(uuid.UUID(str(fid)), friend)

    for friend in friends_list(user_id):
        name = str(friend.get("display_name") or "").lower()
        email = str(friend.get("email") or "").lower()
        if search in name or search in email:
            fid = friend.get("friend_user_id")
            if fid:
                return _recipient_from_user_uuid(uuid.UUID(str(fid)), friend)

    prof = db.user_agent_profile_get(user_id)
    known = prof.get("known_people", []) if prof else []
    for person in known:
        if not isinstance(person, dict):
            continue
        name = str(person.get("name") or "").lower()
        nick = str(person.get("nickname") or "").lower()
        if search in name or search in nick:
            em = str(person.get("email") or "").strip().lower()
            return {
                "display_name": person.get("name") or person.get("nickname") or raw,
                "email": em or None,
                "discord_user_id": str(person.get("discord_user_id") or "").strip() or None,
                "telegram_user_id": str(person.get("telegram_user_id") or "").strip() or None,
                "friend_user_id": None,
                "is_confirmed_friend": False,
            }
    return None


def _recipient_from_user_uuid(friend_user_id: uuid.UUID, friend_row: dict[str, Any]) -> dict[str, Any]:
    tg = db.user_telegram_user_id_get(friend_user_id)
    dc = db.user_discord_user_id_get(friend_user_id)
    return {
        "friend_user_id": str(friend_user_id),
        "display_name": friend_row.get("display_name") or friend_row.get("email"),
        "email": friend_row.get("email"),
        "discord_user_id": dc or friend_row.get("discord_user_id"),
        "telegram_user_id": tg,
        "is_confirmed_friend": True,
    }


def resolve_contact_email(user_id: uuid.UUID, name_or_email: str) -> str | None:
    """Resolve a friend, known person, or raw email to a deliverable email address."""
    raw = (name_or_email or "").strip()
    if not raw:
        return None
    if "@" in raw:
        return raw.lower()
    friend = resolve_friend_by_name(user_id, raw)
    if friend and friend.get("email"):
        return str(friend["email"]).strip().lower()
    prof = db.user_agent_profile_get(user_id)
    known = prof.get("known_people", []) if prof else []
    search = raw.lower()
    for person in known:
        if not isinstance(person, dict):
            continue
        name = str(person.get("name") or "").lower()
        nick = str(person.get("nickname") or "").lower()
        if search in name or search in nick:
            em = str(person.get("email") or "").strip().lower()
            if em:
                return em
    return None


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
