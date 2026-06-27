"""Workspace delegation settings endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.workspace.use_cases import workspace_controller_services as ws_services

router = APIRouter()

class WorkspaceDelegateUpdateBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


@router.get("/{workspace_id}/delegate")
async def get_workspace_delegate(request: Request, workspace_id: str) -> dict[str, Any]:
    """Workspace delegate overlay (merges over global user delegate at runtime)."""
    from apps.backend.domain.delegation.config_schema import default_delegate_config

    user = await get_current_user(request)
    row = ws_services.workspace_retrieval.fetch_workspace_row_shared(workspace_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[2] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        ws_row = ws_services.workspace_delegate_store.get_workspace_delegate(
            workspace_id=uuid.UUID(str(workspace_id))
        )
    except Exception as e:
        return {
            "ok": True,
            "config": default_delegate_config(),
            "updated_at": None,
            "delegate_storage": "unavailable",
            "detail": str(e)[:200],
        }

    if not ws_row:
        return {"ok": True, "config": default_delegate_config(), "updated_at": None}
    return {
        "ok": True,
        "config": ws_row.get("config") or default_delegate_config(),
        "updated_at": ws_row.get("updated_at"),
    }


@router.put("/{workspace_id}/delegate")
async def put_workspace_delegate(
    request: Request, workspace_id: str, body: WorkspaceDelegateUpdateBody
) -> dict[str, Any]:
    user = await get_current_user(request)
    meta = ws_services.fetch_editable_workspace_tenant_name(workspace_id, user.id)
    if not meta:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    tenant_id = int(meta[0])
    try:
        stored = ws_services.workspace_delegate_store.upsert_workspace_delegate(
            tenant_id=tenant_id,
            workspace_id=uuid.UUID(str(workspace_id)),
            config=body.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"delegate storage unavailable — {e}",
        ) from e
    return {
        "ok": True,
        "stored": True,
        "config": stored.get("config"),
        "updated_at": stored.get("updated_at"),
    }
