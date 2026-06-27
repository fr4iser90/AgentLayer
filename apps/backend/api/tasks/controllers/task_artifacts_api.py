"""HTTP API for task artifacts (persisted outputs linked to tasks)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.agent_runtime.task_access import (
    user_may_access_task_row,
    user_may_access_workspace,
)
from apps.backend.application.agent_runtime.use_cases.agent_controller_services import agent_artifacts_store, agent_tasks_store
from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.platform.use_cases.platform_controller_services import db

router = APIRouter(prefix="/v1/task-artifacts", tags=["task-artifacts"])


class ArtifactCreateBody(BaseModel):
    kind: str = Field(default="report", max_length=64)
    summary: str = Field(default="", max_length=2000)
    content: dict[str, Any] = Field(default_factory=dict)
    workspace_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None


@router.post("")
async def create_artifact(request: Request, body: ArtifactCreateBody) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    if body.workspace_id is not None and not user_may_access_workspace(
        user_id=user.id, workspace_id=body.workspace_id
    ):
        raise HTTPException(status_code=403, detail="workspace not accessible")
    if body.task_id is not None:
        trow = agent_tasks_store.get_task(task_id=body.task_id, tenant_id=tenant_id)
        if not trow or not user_may_access_task_row(
            user_id=user.id, tenant_id=tenant_id, row=trow
        ):
            raise HTTPException(status_code=404, detail="task not found")
    row = agent_artifacts_store.create_artifact(
        tenant_id=tenant_id,
        created_by_user_id=user.id,
        kind=body.kind,
        summary=body.summary,
        content=body.content,
        workspace_id=body.workspace_id,
        created_by_task_id=body.task_id,
    )
    if body.task_id is not None:
        agent_tasks_store.update_task(
            task_id=body.task_id,
            tenant_id=tenant_id,
            append_artifact_ref=str(row.get("id")),
        )
    return {"ok": True, "artifact": agent_artifacts_store.row_to_public(row)}


@router.get("/{artifact_id}")
async def get_artifact(request: Request, artifact_id: uuid.UUID) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    row = agent_artifacts_store.get_artifact(artifact_id=artifact_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="artifact not found")
    if row.get("created_by_user_id") != user.id:
        wid = row.get("workspace_id")
        if wid is None or not user_may_access_workspace(user_id=user.id, workspace_id=wid):
            raise HTTPException(status_code=404, detail="artifact not found")
    return {"ok": True, "artifact": agent_artifacts_store.row_to_public(row)}
