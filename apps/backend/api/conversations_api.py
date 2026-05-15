"""Server-synced chat conversations (GET/PUT/POST/DELETE /v1/user/conversations)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.db import db as db_mod
from apps.backend.infrastructure.conversations_db import (
    conversation_create,
    conversation_delete,
    conversation_get,
    conversation_replace,
    conversations_list,
)
from apps.backend.dashboard import db as dashboard_db

router = APIRouter(prefix="/v1/user/conversations", tags=["conversations"])


class MessageItem(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: Any = ""  # str or OpenAI multimodal list


class ConversationCreateBody(BaseModel):
    title: str = Field(default="", max_length=500)
    mode: Literal["chat", "agent"] = "chat"
    model: str = Field(default="", max_length=512)
    messages: list[MessageItem] = Field(default_factory=list)
    agent_log: list[Any] = Field(default_factory=list)
    dashboard_id: uuid.UUID | None = None
    """When true with ``dashboard_id``, creates the one shared thread per dashboard (all members see it)."""
    shared: bool = False
    agent_id: str | None = Field(default=None, max_length=128)
    workspace_id: uuid.UUID | None = None


class ConversationUpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    mode: Literal["chat", "agent"] | None = None
    model: str | None = Field(default=None, max_length=512)
    messages: list[MessageItem] | None = None
    agent_log: list[Any] | None = None
    agent_id: str | None = Field(default=None, max_length=128)
    workspace_id: uuid.UUID | None = None


@router.get("")
async def list_conversations(request: Request, dashboard_id: uuid.UUID | None = None):
    user = await get_current_user(request)
    if dashboard_id is not None:
        tid = db_mod.user_tenant_id(user.id)
        if dashboard_db.dashboard_get(user.id, tid, dashboard_id) is None:
            raise HTTPException(status_code=403, detail="dashboard not accessible")
    return {
        "ok": True,
        "conversations": conversations_list(user.id, dashboard_id=dashboard_id),
    }


@router.post("")
async def create_conversation(request: Request, body: ConversationCreateBody):
    user = await get_current_user(request)
    ws_id = body.dashboard_id
    if body.shared and ws_id is None:
        raise HTTPException(status_code=400, detail="shared requires dashboard_id")
    if ws_id is not None:
        tid = db_mod.user_tenant_id(user.id)
        if dashboard_db.dashboard_get(user.id, tid, ws_id) is None:
            raise HTTPException(status_code=403, detail="dashboard not accessible")
    try:
        data = conversation_create(
            user.id,
            title=body.title,
            mode=body.mode,
            model=body.model,
            messages=[m.model_dump() for m in body.messages],
            agent_log=body.agent_log,
            dashboard_id=ws_id,
            shared=body.shared,
            agent_id=body.agent_id,
            workspace_id=body.workspace_id,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="not allowed to create this conversation") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "conversation": data}


@router.get("/{conversation_id}")
async def get_conversation(request: Request, conversation_id: uuid.UUID):
    user = await get_current_user(request)
    data = conversation_get(user.id, conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True, "conversation": data}


@router.put("/{conversation_id}")
async def put_conversation(
    request: Request, conversation_id: uuid.UUID, body: ConversationUpdateBody
):
    user = await get_current_user(request)
    msgs = None
    if body.messages is not None:
        msgs = [m.model_dump() for m in body.messages]
    prefs: dict[str, Any] | None = None
    fs = body.model_fields_set
    if "agent_id" in fs or "workspace_id" in fs:
        prefs = {}
        if "agent_id" in fs:
            prefs["agent_id"] = body.agent_id
        if "workspace_id" in fs:
            prefs["workspace_id"] = body.workspace_id
    data = conversation_replace(
        user.id,
        conversation_id,
        title=body.title,
        mode=body.mode,
        model=body.model,
        messages=msgs,
        agent_log=body.agent_log,
        composer_prefs=prefs,
    )
    if not data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True, "conversation": data}


@router.delete("/{conversation_id}")
async def delete_conversation(request: Request, conversation_id: uuid.UUID):
    user = await get_current_user(request)
    if not conversation_delete(user.id, conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True, "deleted": True}
