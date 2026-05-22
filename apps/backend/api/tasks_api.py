"""HTTP API for tasks (user-scoped backlog)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.agent_task_access import (
    user_may_access_task_row,
    user_may_access_workspace,
)
from apps.backend.infrastructure import agent_artifacts_store, agent_tasks_store
from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.db import db

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class TaskCreateBody(BaseModel):
    scope: Literal["global", "workspace"] = "global"
    goal: str = Field(..., min_length=1, max_length=16000)
    task_type: str = Field(default="general", max_length=128)
    workspace_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    status: str = Field(default="draft", max_length=32)
    priority: Literal["low", "normal", "high"] = "normal"
    assigned_agent_id: str | None = Field(default=None, max_length=128)
    requirements: list[Any] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class TaskPatchBody(BaseModel):
    status: str | None = None
    goal: str | None = Field(default=None, max_length=16000)
    priority: Literal["low", "normal", "high"] | None = None
    assigned_agent_id: str | None = Field(default=None, max_length=128)
    append_artifact_ref: str | None = None


@router.post("")
async def create_task(request: Request, body: TaskCreateBody) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    if body.scope == "workspace":
        if body.workspace_id is None:
            raise HTTPException(status_code=400, detail="workspace_id required for workspace scope")
        if not user_may_access_workspace(user_id=user.id, workspace_id=body.workspace_id):
            raise HTTPException(status_code=403, detail="workspace not accessible")
    try:
        row = agent_tasks_store.create_task(
            tenant_id=tenant_id,
            created_by_user_id=user.id,
            scope=body.scope,
            goal=body.goal,
            task_type=body.task_type,
            workspace_id=body.workspace_id,
            parent_task_id=body.parent_task_id,
            conversation_id=body.conversation_id,
            status=body.status,  # type: ignore[arg-type]
            priority=body.priority,
            assigned_agent_id=body.assigned_agent_id,
            requirements=body.requirements,
            artifact_refs=body.artifact_refs,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "task": agent_tasks_store.row_to_public(row)}


@router.get("")
async def list_tasks(
    request: Request,
    scope: Literal["global", "workspace"] | None = None,
    workspace_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    root_only: bool = False,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    if workspace_id is not None and not user_may_access_workspace(
        user_id=user.id, workspace_id=workspace_id
    ):
        raise HTTPException(status_code=403, detail="workspace not accessible")
    rows = agent_tasks_store.list_tasks(
        tenant_id=tenant_id,
        created_by_user_id=user.id,
        scope=scope,
        workspace_id=workspace_id,
        parent_task_id=parent_task_id,
        status=status,
        limit=limit,
    )
    if root_only:
        rows = [r for r in rows if r.get("parent_task_id") is None]
    return {"ok": True, "tasks": [agent_tasks_store.row_to_public(r) for r in rows]}


@router.get("/{task_id}")
async def get_task(request: Request, task_id: uuid.UUID) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    row = agent_tasks_store.get_task(task_id=task_id, tenant_id=tenant_id)
    if not row or not user_may_access_task_row(
        user_id=user.id, tenant_id=tenant_id, row=row
    ):
        raise HTTPException(status_code=404, detail="task not found")
    subs = agent_tasks_store.list_subtasks(
        tenant_id=tenant_id, parent_task_id=task_id, limit=100
    )
    arts = agent_artifacts_store.list_artifacts_for_task(
        tenant_id=tenant_id, task_id=task_id, limit=50
    )
    return {
        "ok": True,
        "task": agent_tasks_store.row_to_public(row),
        "subtasks": [agent_tasks_store.row_to_public(s) for s in subs],
        "artifacts": [agent_artifacts_store.row_to_public(a) for a in arts],
    }


@router.patch("/{task_id}")
async def patch_task(request: Request, task_id: uuid.UUID, body: TaskPatchBody) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    row = agent_tasks_store.get_task(task_id=task_id, tenant_id=tenant_id)
    if not row or not user_may_access_task_row(
        user_id=user.id, tenant_id=tenant_id, row=row
    ):
        raise HTTPException(status_code=404, detail="task not found")
    updated = agent_tasks_store.update_task(
        task_id=task_id,
        tenant_id=tenant_id,
        status=body.status,  # type: ignore[arg-type]
        goal=body.goal,
        priority=body.priority,
        assigned_agent_id=body.assigned_agent_id,
        append_artifact_ref=body.append_artifact_ref,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="update failed")
    return {"ok": True, "task": agent_tasks_store.row_to_public(updated)}
