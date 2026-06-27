"""Admin-only workspace maintenance (reindex)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.identity.use_cases.request_auth import get_current_user, require_admin
from apps.backend.application.workspace.use_cases import workspace_controller_services as ws_services

from apps.backend.api.workspaces.controllers.workspaces_api import WorkspaceIndexBody

router = APIRouter(prefix="/v1/admin/workspaces", tags=["workspaces-admin"])


@router.post("/{workspace_id}/reindex")
async def admin_reindex_workspace(
    request: Request, workspace_id: str, body: WorkspaceIndexBody | None = None
) -> dict[str, Any]:
    """Start full/code/docs reindex for any workspace (admin)."""
    await require_admin(request)
    await get_current_user(request)

    row = ws_services.fetch_workspace_row_any_owner(workspace_id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    mode = (body.mode if body else "full").strip().lower()
    if mode not in ("full", "code", "docs"):
        mode = "full"
    max_files = body.max_files if body else 5000

    kick = ws_services.workspace_retrieval.start_semantic_index_async(
        workspace_id, row[3], max_files=max_files, mode=mode
    )
    status = ws_services.workspace_retrieval.index_status_payload(row)
    return {
        "ok": True,
        "workspace": ws_services.row_to_workspace(row),
        "started": bool(kick.get("started")),
        "already_running": bool(kick.get("already_running")),
        "job": kick.get("job"),
        "status": status,
    }
