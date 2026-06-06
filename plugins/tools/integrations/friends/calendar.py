"""
Get calendar entries from a friend who has shared his calendar with you.
Call this tool automatically when the user asks about availability, appointments or schedule of another person.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.domain.shares.policy import effective_days_ahead
from apps.backend.infrastructure.db.share_permissions_db import (
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    share_permission_get,
)

from apps.backend.domain.friends.common import (
    friend_calendar_ics_url,
    resolve_friend_by_name,
)

__version__ = "1.0.0"
TOOL_ID = "calendar"
TOOL_BUCKET = "core"
TOOL_DOMAIN = "friends"
TOOL_TRIGGERS = (
    "wann muss",
    "wann wieder",
    "wann muss NAME wieder auf arbeit",
    "arbeit",
    "schicht",
    "dienst",
    "arbeitszeit",
    "schichtplan",
    "nächste schicht",
    "wann bin ich",
    "wann ist er",
    "wann ist sie",
    "frei am",
    "zeit am",
    "termine",
    "termin",
    "kalender",
)
TOOL_CAPABILITIES = ("friends.calendar", "default")


def calendar(arguments: dict[str, Any]) -> Any:
    """
    Get calendar entries from a friend who has shared his calendar with you.
    Call this tool automatically when the user asks about availability, appointments or schedule of another person.
    
    This tool will:
    1. Resolve the person by name from your friends list
    2. Check if that friend has shared his calendar with you
    3. If allowed, retrieve upcoming appointments
    """
    _tid, requesting_user_id = get_identity()
    if not requesting_user_id:
        return {"error": "no user identity available"}

    try:
        import logging
        import json
        logger = logging.getLogger(__name__)
        
        # First check for auto filled entity parameter from trigger system, then fall back to name
        name_query = arguments.get("entity") or arguments.get("name") or arguments.get("friend") or arguments.get("friend_name")
        logger.info("🔍 get_friend_calendar CALLED with arguments: %s | name_query=%s", arguments, name_query)
        
        if not name_query:
            logger.warning("❌ get_friend_calendar: NO NAME PARAMETER")
            return json.dumps({"error": "name or entity parameter is required"}, ensure_ascii=False)

        # Step 1: Find friend by name
        friend_user = resolve_friend_by_name(requesting_user_id, str(name_query))
        
        if not friend_user:
            res = {
                "result": f"Could not find {name_query} in your friends list. Only confirmed friends can share calendars."
            }
            logger.info("✅ get_friend_calendar RESULT: %s", res)
            return json.dumps(res, ensure_ascii=False)
        
        friend_user_id = uuid.UUID(friend_user["friend_user_id"])
        friend_display_name = friend_user.get("display_name") or friend_user.get("email")

        # Step 2: Check share permission (google_calendar + legacy calendar alias)
        has_access = share_permission_check_resolved(
            owner_user_id=friend_user_id,
            grantee_user_id=requesting_user_id,
            resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
            resource_identifier="primary",
        )
        
        if not has_access:
            res = {
                "result": f"{friend_display_name} has not shared their calendar with you."
            }
            logger.info("✅ get_friend_calendar RESULT: %s", res)
            return json.dumps(res, ensure_ascii=False)

        # Step 3: Get friend's ICS calendar URL (google_calendar or calendar_ics secret)
        ics_url = friend_calendar_ics_url(friend_user_id)
        
        if not ics_url:
            res = {
                "result": f"{friend_display_name} has a calendar connected but no sharing is configured."
            }
            logger.info("✅ get_friend_calendar RESULT: %s", res)
            return json.dumps(res, ensure_ascii=False)

        # Step 4: Delegate to existing calendar parser
        # Import dynamically to avoid circular dependencies
        try:
            from plugins.tools.personal.calendar.ics import calendar_ics
            
            requested_days = arguments.get("days", 7)
            effective_days = effective_days_ahead(
                grant.get("policy"),
                requested_days if requested_days is not None else None,
            )
            calendar_result = calendar_ics({
                "ics_url": ics_url,
                "days": effective_days,
            })

            res = {
                "friend_name": friend_display_name,
                "days_requested": requested_days,
                "days_effective": effective_days,
                "share_policy": grant.get("policy") or {},
                "calendar": calendar_result,
            }
            logger.info("✅ get_friend_calendar RESULT: %s", res)
            return json.dumps(res, ensure_ascii=False)
            
        except ImportError:
            res = {
                "friend_name": friend_display_name,
                "result": "Calendar access granted but calendar parser is not available."
            }
            logger.info("✅ get_friend_calendar RESULT: %s", res)
            return json.dumps(res, ensure_ascii=False)

    except Exception as e:
        res = {"error": str(e)}
        logger.warning("❌ get_friend_calendar EXCEPTION: %s", str(e))
        return json.dumps(res, ensure_ascii=False)


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
                                "This will be matched against your friends list. ❗ REQUIRED PARAMETER. "
                                "PREFER TO PASS THE EMAIL ADDRESS WHEN AVAILABLE, IT IS UNIQUE AND MORE RELIABLE."
                            ),
                        },
                        "entity": {
                            "type": "string",
                            "TOOL_DESCRIPTION": (
                                "GET FRIEND WORK SCHEDULE AND CALENDAR. "
                                "⚠️ CALL THIS TOOL DIRECTLY FIRST. DO NOT CALL get_friend_info BEFORE. DO NOT CALL get_tool_help. "
                                "This tool resolves the friend name automatically, checks permissions and returns calendar entries. "
                                "Use this when user asks: 'when is NAME working', 'when must NAME go to work', 'work schedule', 'shifts'. "
                                "You do not need any other tools before this."
                            ),
                            "default": 7
                        }
                    },
                    "required": ["name"]
                },
        },
    },
]