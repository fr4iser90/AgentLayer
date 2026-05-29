"""
List share permissions between you and friends (what you share / what they share with you).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db.share_permissions_db import (
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    list_shares_between,
    list_shares_by_grantee,
    list_shares_by_owner,
    share_permission_check_resolved,
)

from plugins.tools.capabilities.platform.friends.friends_common import (
    resource_type_label,
    resolve_friend_by_name,
)

__version__ = "1.0.0"
TOOL_ID = "get_friend_shares"
TOOL_BUCKET = "core"
TOOL_DOMAIN = "friends"
TOOL_TRIGGERS = (
    "was teilt",
    "was share",
    "was hat",
    "geteilt",
    "sharing",
    "shares",
    "freigabe",
    "freigaben",
    "zugriff auf",
    "wer darf",
    "wer hat zugriff",
)
TOOL_CAPABILITIES = ("friends.shares", "default")


def _normalize_share_rows(rows: list[dict[str, Any]], *, direction: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        resource_type = str(row.get("resource_type") or "").strip().lower()
        if not resource_type:
            continue
        peer_id = row.get("grantee_user_id") if direction == "outgoing" else row.get("owner_user_id")
        out.append(
            {
                "resource_type": resource_type,
                "resource_label": resource_type_label(resource_type),
                "peer_user_id": str(peer_id) if peer_id else None,
                "peer_display_name": row.get("display_name") or row.get("email"),
                "peer_email": row.get("email"),
            }
        )
    return out


def _group_shares_by_peer(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        peer_id = row.get("peer_user_id") or ""
        if peer_id not in grouped:
            grouped[peer_id] = {
                "user_id": peer_id,
                "display_name": row.get("peer_display_name"),
                "email": row.get("peer_email"),
                "resources": [],
            }
        grouped[peer_id]["resources"].append(
            {
                "resource_type": row["resource_type"],
                "resource_label": row["resource_label"],
            }
        )
    return list(grouped.values())


def _shares_for_friend(requesting_user_id: uuid.UUID, friend_user_id: uuid.UUID) -> dict[str, Any]:
    between = list_shares_between(requesting_user_id, friend_user_id)
    outgoing = [
        {
            "resource_type": rt,
            "resource_label": resource_type_label(rt),
            "granted": True,
        }
        for rt in between.get("outgoing") or []
    ]
    incoming = [
        {
            "resource_type": rt,
            "resource_label": resource_type_label(rt),
            "granted": True,
        }
        for rt in between.get("incoming") or []
    ]
    calendar_incoming = share_permission_check_resolved(
        owner_user_id=friend_user_id,
        grantee_user_id=requesting_user_id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    )
    calendar_outgoing = share_permission_check_resolved(
        owner_user_id=requesting_user_id,
        grantee_user_id=friend_user_id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    )
    return {
        "you_share_with_them": outgoing,
        "they_share_with_you": incoming,
        "calendar_access_you_have": calendar_incoming,
        "calendar_access_they_have": calendar_outgoing,
    }


def get_friend_shares(arguments: dict[str, Any]) -> str:
    """Return share permissions for one friend or summarize all friend shares."""
    _tid, requesting_user_id = get_identity()
    if not requesting_user_id:
        return json.dumps({"error": "no user identity available"}, ensure_ascii=False)

    try:
        name_query = (
            arguments.get("entity")
            or arguments.get("name")
            or arguments.get("friend")
            or arguments.get("friend_name")
        )
        if name_query:
            friend = resolve_friend_by_name(requesting_user_id, str(name_query))
            if not friend:
                return json.dumps(
                    {
                        "ok": False,
                        "result": f"Could not find {name_query} in your friends list.",
                    },
                    ensure_ascii=False,
                )
            friend_user_id = uuid.UUID(friend["friend_user_id"])
            payload = {
                "ok": True,
                "friend": {
                    "user_id": str(friend_user_id),
                    "display_name": friend.get("display_name") or friend.get("email"),
                    "email": friend.get("email"),
                },
                **_shares_for_friend(requesting_user_id, friend_user_id),
            }
            return json.dumps(payload, ensure_ascii=False)

        outgoing = _normalize_share_rows(
            list_shares_by_owner(requesting_user_id),
            direction="outgoing",
        )
        incoming = _normalize_share_rows(
            list_shares_by_grantee(requesting_user_id),
            direction="incoming",
        )
        return json.dumps(
            {
                "ok": True,
                "outgoing_by_friend": _group_shares_by_peer(outgoing),
                "incoming_by_friend": _group_shares_by_peer(incoming),
                "outgoing_count": len(outgoing),
                "incoming_count": len(incoming),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "get_friend_shares": get_friend_shares,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_friend_shares",
            "TOOL_DESCRIPTION": (
                "List what you share with friends and what friends share with you "
                "(Google Calendar, GitHub, Todoist, notes, roadmap). "
                "Pass a friend name or email for one person; omit name for a full summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional friend name or email. When set, returns bidirectional share "
                            "status for that friend only."
                        ),
                    },
                    "entity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Auto-filled name/email from the trigger system.",
                    },
                },
            },
        },
    },
]
