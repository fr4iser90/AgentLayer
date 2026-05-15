"""
Get information about known people / friends from the user's contact list.
Call this tool ONLY when the user asks about a specific person or friend.
"""

from __future__ import annotations

from typing import Any, Callable
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "get_friend_info"
TOOL_BUCKET = "core"
TOOL_DOMAIN = "friends"
TOOL_TRIGGERS = (
    "wer ist",
    "wer ist das",
    "information über",
    "kontakt von",
    "email von",
    "telefonnummer von",
    "bekannte person",
    "@",
    ".com",
    ".de",
    "@gmail.com",
    "@outlook.com",
    "@hotmail.com",
)
TOOL_CAPABILITIES = ("friends.user", "default")


def get_friend_info(arguments: dict[str, Any]) -> Any:
    """
    Get information about known people / friends from the user's contact list.
    Call this tool ONLY when the user asks about a specific person or friend.
    """
    _tid, uid = get_identity()
    if not uid:
        return []

    try:
        # First get confirmed friends from database
        friends = db.friends_list(uid)
        
        # Merge with known_people from profile
        prof = db.user_agent_profile_get(uid)
        known_people = prof.get("known_people", []) if prof else []

        # First check for auto filled entity parameter from trigger system, then fall back to name
        name_query = arguments.get("entity") or arguments.get("name")
        if not name_query:
            return {
                "friends": friends,
                "known_people": known_people
            }

        # Search for person by name (case insensitive)
        search_name = name_query.strip().lower()
        matches = []

        # Search in confirmed friends first
        for friend in friends:
            name = friend.get("display_name", "").lower()
            email = friend.get("email", "").lower()
            if search_name in name or search_name in email:
                matches.append({
                    **friend,
                    "is_confirmed_friend": True
                })

        # Then search in known_people
        for person in known_people:
            if not isinstance(person, dict):
                continue

            name = person.get("name", "").lower()
            nickname = person.get("nickname", "").lower()

            if search_name in name or search_name in nickname:
                matches.append(person)

        return matches

    except Exception as e:
        return {"error": str(e)}


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "get_friend_info": get_friend_info,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_friend_info",
            "TOOL_DESCRIPTION": (
                "Get information about known people / friends from the user's contact list. "
                "Call this tool ONLY when the user asks about a specific person or friend. "
                "Search works with full name and nickname."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Name of the person to get information about. If empty, returns all known people."
                        ),
                    },
                    "entity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Auto filled by trigger system. Contains the extracted name/email from user message."
                        ),
                    }
                },
            },
        },
    },
]
