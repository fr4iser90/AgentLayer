"""Server-synced chat conversations (GET/PUT/POST/DELETE /v1/user/conversations)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.db import db as db_mod
from apps.backend.domain.agent_task_access import user_may_access_task_row
from apps.backend.infrastructure import agent_tasks_store
from apps.backend.infrastructure.conversations_db import (
    conversation_create,
    conversation_delete,
    conversation_get,
    conversation_replace,
    conversation_update_delegate_prefs,
    conversations_list,
)
from apps.backend.dashboard import db as dashboard_db

router = APIRouter(prefix="/v1/user/conversations", tags=["conversations"])


class MessageItem(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: Any = ""  # str or OpenAI multimodal list
    created_at: str | None = None  # ISO-8601; preserved on save when provided


# Legacy: JSON array of timeline entries. Current UI: v2 object ``{v, current, turns}``.
AgentLogPayload = list[Any] | dict[str, Any]


class ConversationCreateBody(BaseModel):
    title: str = Field(default="", max_length=500)
    mode: Literal["chat", "agent"] = "chat"
    model: str = Field(default="", max_length=512)
    messages: list[MessageItem] = Field(default_factory=list)
    agent_log: AgentLogPayload = Field(default_factory=list)
    dashboard_id: uuid.UUID | None = None
    """When true with ``dashboard_id``, creates the one shared thread per dashboard (all members see it)."""
    shared: bool = False
    agent_id: str | None = Field(default=None, max_length=128)
    workspace_id: uuid.UUID | None = None
    model_catalog_owned_by: str | None = Field(default=None, max_length=64)
    active_task_id: uuid.UUID | None = None


class ConversationActiveTaskBody(BaseModel):
    active_task_id: uuid.UUID | None = None


class ConversationUpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    mode: Literal["chat", "agent"] | None = None
    model: str | None = Field(default=None, max_length=512)
    messages: list[MessageItem] | None = None
    agent_log: AgentLogPayload | None = None
    agent_id: str | None = Field(default=None, max_length=128)
    workspace_id: uuid.UUID | None = None
    model_catalog_owned_by: str | None = Field(default=None, max_length=64)
    active_task_id: uuid.UUID | None = None


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
            model_catalog_owned_by=body.model_catalog_owned_by,
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
    if (
        "agent_id" in fs
        or "workspace_id" in fs
        or "model_catalog_owned_by" in fs
        or "active_task_id" in fs
    ):
        prefs = {}
        if "agent_id" in fs:
            prefs["agent_id"] = body.agent_id
        if "workspace_id" in fs:
            prefs["workspace_id"] = body.workspace_id
        if "model_catalog_owned_by" in fs:
            prefs["model_catalog_owned_by"] = body.model_catalog_owned_by
        if "active_task_id" in fs:
            if body.active_task_id is not None:
                tenant_id = db_mod.user_tenant_id(user.id)
                trow = agent_tasks_store.get_task(
                    task_id=body.active_task_id, tenant_id=tenant_id
                )
                if not trow or not user_may_access_task_row(
                    user_id=user.id, tenant_id=tenant_id, row=trow
                ):
                    raise HTTPException(status_code=404, detail="task not found")
            prefs["active_task_id"] = body.active_task_id
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


@router.patch("/{conversation_id}/active-task")
async def set_conversation_active_task(
    request: Request, conversation_id: uuid.UUID, body: ConversationActiveTaskBody
) -> dict:
    user = await get_current_user(request)
    tenant_id = db_mod.user_tenant_id(user.id)
    if body.active_task_id is not None:
        trow = agent_tasks_store.get_task(
            task_id=body.active_task_id, tenant_id=tenant_id
        )
        if not trow or not user_may_access_task_row(
            user_id=user.id, tenant_id=tenant_id, row=trow
        ):
            raise HTTPException(status_code=404, detail="task not found")
    with db_mod.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_conversations
                SET active_task_id = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                """,
                (body.active_task_id, conversation_id, user.id),
            )
            if cur.rowcount < 1:
                raise HTTPException(status_code=404, detail="conversation not found")
        conn.commit()
    return {
        "ok": True,
        "active_task_id": str(body.active_task_id) if body.active_task_id else None,
    }


@router.delete("/{conversation_id}")
async def delete_conversation(request: Request, conversation_id: uuid.UUID):
    user = await get_current_user(request)
    if not conversation_delete(user.id, conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True, "deleted": True}


class ConversationDelegatePrefsBody(BaseModel):
    delegate_auto_respond_enabled: bool | None = None
    delegate_auto_respond_after_sec: int | None = Field(default=None, ge=15, le=600)
    delegate_max_chain_turns: int | None = Field(default=None, ge=1, le=10)


@router.patch("/{conversation_id}/delegate-prefs")
async def patch_conversation_delegate_prefs(
    request: Request,
    conversation_id: uuid.UUID,
    body: ConversationDelegatePrefsBody,
) -> dict:
    user = await get_current_user(request)
    try:
        data = conversation_update_delegate_prefs(
            user.id,
            conversation_id,
            delegate_auto_respond_enabled=body.delegate_auto_respond_enabled,
            delegate_auto_respond_after_sec=body.delegate_auto_respond_after_sec,
            delegate_max_chain_turns=body.delegate_max_chain_turns,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)[:200]) from e
    if not data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "ok": True,
        "delegate_auto_respond_enabled": data.get("delegate_auto_respond_enabled"),
        "delegate_auto_respond_after_sec": data.get("delegate_auto_respond_after_sec"),
        "delegate_max_chain_turns": data.get("delegate_max_chain_turns"),
    }


@router.post("/{conversation_id}/delegate-respond")
async def post_conversation_delegate_respond(
    request: Request,
    conversation_id: uuid.UUID,
) -> dict:
    """Idle auto-respond: delegate decides next step; client appends synthetic user message."""
    user = await get_current_user(request)
    tenant_id = db_mod.user_tenant_id(user.id)
    conv = conversation_get(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if not conv.get("delegate_auto_respond_enabled"):
        raise HTTPException(status_code=400, detail="delegate auto-respond is disabled for this conversation")

    from apps.backend.domain.delegate_decision import run_delegate_decision
    from apps.backend.infrastructure import delegate_runs_store, user_delegate_store, workspace_delegate_store
    from apps.backend.infrastructure.db import db

    max_chain = int(conv.get("delegate_max_chain_turns") or 3)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int FROM delegate_runs
                WHERE conversation_id = %s
                  AND user_id = %s
                  AND created_at > now() - interval '2 hours'
                  AND outcome NOT IN ('escalated', 'denied')
                """,
                (conversation_id, user.id),
            )
            chain_count = int((cur.fetchone() or [0])[0])
    if chain_count >= max_chain:
        raise HTTPException(
            status_code=429,
            detail=f"delegate chain limit reached ({max_chain} turns)",
        )

    user_cfg_row = user_delegate_store.get_user_delegate(user_id=user.id)
    user_cfg = (user_cfg_row or {}).get("config")
    ws_cfg = None
    ws_label = None
    pref_ws = conv.get("workspace_id")
    if pref_ws:
        try:
            ws_uuid = uuid.UUID(str(pref_ws))
            ws_row = workspace_delegate_store.get_workspace_delegate(workspace_id=ws_uuid)
            ws_cfg = (ws_row or {}).get("config")
            ws_label = str(pref_ws)
        except ValueError:
            pass

    task_goal = None
    task_req = None
    active_task_id = conv.get("active_task_id")
    if active_task_id:
        try:
            trow = agent_tasks_store.get_task(
                task_id=uuid.UUID(str(active_task_id)), tenant_id=tenant_id
            )
            if trow:
                task_goal = str(trow.get("goal") or "")
                task_req = str(trow.get("requirements") or "")
        except ValueError:
            pass

    messages = conv.get("messages") or []
    try:
        decision = run_delegate_decision(
            messages=messages,
            user_config=user_cfg,
            workspace_config=ws_cfg,
            workspace_label=ws_label,
            task_goal=task_goal,
            task_requirements=task_req,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"delegate decision failed: {e}") from e

    if decision.get("escalate"):
        try:
            delegate_runs_store.insert_delegate_run(
                tenant_id=tenant_id,
                user_id=user.id,
                conversation_id=conversation_id,
                trigger="idle",
                decision_summary=str(decision.get("decision_summary") or ""),
                synthetic_user_message="",
                outcome="escalated",
                chain_index=chain_count,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail=str(decision.get("escalate_reason") or "delegate escalated"),
        )

    synthetic = str(decision.get("synthetic_user_message") or "").strip()
    if not synthetic:
        raise HTTPException(status_code=502, detail="delegate returned empty synthetic message")

    run_row = delegate_runs_store.insert_delegate_run(
        tenant_id=tenant_id,
        user_id=user.id,
        conversation_id=conversation_id,
        trigger="idle",
        decision_summary=str(decision.get("decision_summary") or ""),
        synthetic_user_message=synthetic,
        outcome="started",
        chain_index=chain_count,
    )
    return {
        "ok": True,
        "delegate_run_id": run_row.get("id"),
        "decision_summary": decision.get("decision_summary"),
        "synthetic_user_message": synthetic,
        "stand_in_marker": "[Stand-in · auto]",
    }
