"""Send friend requests to other AgentLayer users by email or contact name."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.friends.common import resolve_contact_email
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.auth import get_user_by_email
from apps.backend.infrastructure.db.friends_db import (
    friend_get,
    friend_request_create,
    friend_request_get_between,
)

__version__ = "1.0.0"
TOOL_ID = "request"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "friends"
# Router phrases: co-located request.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("friends.request", "default")


def send_request(arguments: dict[str, Any]) -> str:
    """Send a friend request by email or known contact name."""
    tid, uid = get_identity()
    if uid is None:
        return json.dumps({"ok": False, "error": "No user identity"}, ensure_ascii=False)

    email_raw = str(
        arguments.get("email") or arguments.get("name") or arguments.get("entity") or ""
    ).strip()
    if not email_raw:
        return json.dumps({"ok": False, "error": "email or name is required"}, ensure_ascii=False)

    email = email_raw.lower() if "@" in email_raw else (resolve_contact_email(uid, email_raw) or "")
    if not email:
        return json.dumps(
            {"ok": False, "error": f"could not resolve email for {email_raw!r}"},
            ensure_ascii=False,
        )

    target = get_user_by_email(email)
    if target is None:
        return json.dumps(
            {
                "ok": False,
                "error": f"no AgentLayer account for {email} — they must register first",
            },
            ensure_ascii=False,
        )
    if target.id == uid:
        return json.dumps({"ok": False, "error": "cannot send friend request to yourself"}, ensure_ascii=False)

    if friend_get(uid, target.id):
        return json.dumps(
            {"ok": False, "error": f"already friends with {email}"},
            ensure_ascii=False,
        )

    if friend_request_get_between(uid, target.id):
        return json.dumps(
            {"ok": False, "error": f"friend request to {email} already pending"},
            ensure_ascii=False,
        )

    message = str(arguments.get("message") or "").strip()[:500] or None
    ok = friend_request_create(tid, uid, target.id, message)
    if not ok:
        return json.dumps({"ok": False, "error": "could not create friend request"}, ensure_ascii=False)

    return json.dumps(
        {
            "ok": True,
            "email": email,
            "target_user_id": str(target.id),
            "message": message,
            "hint": "They will see the request under Settings → Friends and can accept it.",
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "send_request": send_request,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send_request",
            "TOOL_DESCRIPTION": (
                "Send a friend request to another AgentLayer user by email or contact name. "
                "Required before friends.shares can grant collection/dashboard access across tenants."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "TOOL_DESCRIPTION": "Recipient email"},
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Contact/friend name if email is unknown",
                    },
                    "entity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Auto-filled name from trigger system",
                    },
                    "message": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional short note with the request (max 500 chars)",
                    },
                },
            },
        },
    },
]
