"""Chat message feedback API (thumbs up/down)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.agent_runtime.use_cases.message_feedback import (
    get_conversation_for_feedback,
    list_feedback_for_admin,
    list_feedback_for_conversation,
    upsert_feedback_for_message,
)
from apps.backend.application.identity.use_cases.request_auth import get_current_user, require_admin

router = APIRouter(prefix="/v1/user/conversations", tags=["message-feedback"])


class MessageFeedbackBody(BaseModel):
    message_position: int = Field(ge=0, le=100_000)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)


@router.get("/{conversation_id}/feedback")
async def list_conversation_feedback(request: Request, conversation_id: uuid.UUID) -> dict:
    user = await get_current_user(request)
    if not get_conversation_for_feedback(user.id, conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    try:
        items = list_feedback_for_conversation(
            user_id=user.id,
            conversation_id=conversation_id,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)[:200]) from e
    return {"ok": True, "feedback": items}


@router.put("/{conversation_id}/feedback")
async def upsert_message_feedback(
    request: Request,
    conversation_id: uuid.UUID,
    body: MessageFeedbackBody,
) -> dict:
    user = await get_current_user(request)
    conv = get_conversation_for_feedback(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    msgs = conv.get("messages") or []
    if body.message_position >= len(msgs):
        raise HTTPException(status_code=400, detail="message_position out of range")
    role = (msgs[body.message_position] or {}).get("role")
    if role != "assistant":
        raise HTTPException(status_code=400, detail="feedback only allowed on assistant messages")
    rating = 1 if body.rating == "up" else -1
    try:
        row = upsert_feedback_for_message(
            user_id=user.id,
            conversation_id=conversation_id,
            message_position=body.message_position,
            rating=rating,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)[:200]) from e
    return {"ok": True, "feedback": row}


admin_router = APIRouter(prefix="/v1/admin/message-feedback", tags=["message-feedback-admin"])


@admin_router.get("")
async def admin_list_feedback(request: Request, limit: int = 100) -> dict:
    admin = await require_admin(request)
    items = list_feedback_for_admin(admin_user_id=admin.id, limit=limit)
    return {"ok": True, "feedback": items}
