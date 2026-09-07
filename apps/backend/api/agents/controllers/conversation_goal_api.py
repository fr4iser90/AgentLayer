"""HTTP API for a conversation's ongoing goal (the goal bar's pause/resume/edit/clear).

Creating a goal and writing todos happen through agent tools, not HTTP — this endpoint
exists only for the controls the user drives from the chat UI.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.agent_runtime.use_cases import conversation_goal_service as goals

router = APIRouter(prefix="/v1/user/conversations", tags=["conversations"])


class GoalUpdateBody(BaseModel):
    goal_id: str
    revision: int = Field(ge=1)
    action: Literal["edit", "pause", "resume", "complete", "blocked", "clear"]
    objective: str | None = None
    blocked_reason: str | None = None


@router.patch("/{conversation_id}/goal")
async def update_goal(
    conversation_id: uuid.UUID,
    body: GoalUpdateBody,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    try:
        saved = goals.update_goal(
            user.id,
            conversation_id,
            goal_id=body.goal_id,
            revision=body.revision,
            action=body.action,
            objective=body.objective,
            blocked_reason=body.blocked_reason,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"goal": saved.get("goal") if saved else None}
