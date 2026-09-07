"""Application service for a conversation's ongoing goal.

Only the UI-driven goal transitions live here. Creating goals and writing todos are agent
tool calls that go straight to the store (see plugins/tools/platform/conversation_goal).
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.agent_runtime.conversation_goal import apply_goal_update
from apps.backend.infrastructure.agent_runtime import conversation_goal_store as store


def update_goal(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    goal_id: str,
    revision: int,
    action: str,
    objective: str | None = None,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    row = store.get_conversation_goal(user_id, conversation_id)
    if row is None:
        raise LookupError("conversation not found")
    if action == "clear":
        saved = store.set_session_goal(user_id, conversation_id, None)
        if saved is None:
            raise LookupError("conversation not found")
        return saved
    updated = apply_goal_update(
        row.get("goal") if isinstance(row.get("goal"), dict) else None,
        goal_id=goal_id,
        revision=revision,
        action=action,
        objective=objective,
        blocked_reason=blocked_reason,
    )
    saved = store.set_session_goal(user_id, conversation_id, updated)
    if saved is None:
        raise LookupError("conversation not found")
    return saved
