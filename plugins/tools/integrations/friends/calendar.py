"""Read a friend's shared calendar (ADR 0014 step 4).

A thin alias over the generic share read path. It exists only so the
existing tool name keeps working while the read itself lives in one place:
``shares(action="read")`` → registry → ``CalendarShareAdapter``.

Nothing here checks a grant, resolves a secret or decides a horizon. The
adapter does the grant check, ``fetch_shared_calendar`` resolves and guards
the ICS bearer credential, and the grant caps the horizon. Duplicating any
of that in this module is what step 4 removes — a per-type read tool is a
second place to get the enforcement wrong, and four of seven types already
did (§1.3).
"""
from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.integrations.friends.shares import shares

__version__ = "2.0.0"
TOOL_ID = "calendar"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "friends"
# Router phrases: co-located calendar.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("friends.calendar", "default")


def calendar(arguments: dict[str, Any]) -> str:
    """Get calendar entries from a friend who has shared their calendar."""
    args = dict(arguments or {})
    args["action"] = "read"
    args["resource_type"] = "google_calendar"

    raw = json.loads(shares(args))

    if not raw.get("ok"):
        return json.dumps({"result": raw.get("result", "Could not read the calendar.")}, ensure_ascii=False)

    projection = raw.get("data") or {}
    friend = raw.get("friend") or {}
    return json.dumps(
        {
            "friend_name": friend.get("display_name"),
            "days_requested": args.get("days", 7),
            "days_effective": projection.get("days_effective"),
            "share_policy": projection.get("share_policy") or {},
            "calendar": projection,
        },
        ensure_ascii=False,
        default=str,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "calendar": calendar,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calendar",
            "TOOL_DESCRIPTION": (
                "Get calendar entries from a friend who has shared his calendar with you. "
                "CALL THIS TOOL WITH NAME OR EMAIL OF THE FRIEND. "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Name OR EMAIL of the friend whose calendar you want to see. "
                            "This will be matched against your friends list. Required parameter. "
                            "Prefer the email address when available; it is unique and more reliable."
                        ),
                    },
                    "days": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": (
                            "How many days ahead to read. The friend's grant caps it — asking "
                            "for more returns the granted horizon, not more. "
                            "The answer reports days_effective."
                        ),
                        "default": 7,
                    },
                    "entity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Get friend work schedule and calendar. "
                            "Call this tool directly first. Do not call get_friend_info before. "
                            "Do not call get_tool_help. "
                            "This tool resolves the friend name automatically, checks permissions and returns calendar entries. "
                            "Use when user asks: 'when is NAME working', 'when must NAME go to work', 'work schedule', 'shifts'. "
                            "You do not need any other tools before this."
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
]
