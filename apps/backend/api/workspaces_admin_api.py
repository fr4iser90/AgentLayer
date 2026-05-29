"""Admin-only workspace maintenance (reindex)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from apps.backend.infrastructure.auth import get_current_user, require_admin
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api

from apps.backend.api.workspaces_api import WorkspaceIndexBody

router = APIRouter(prefix="/v1/admin/workspaces", tags=["workspaces-admin"])


@router.post("/{workspace_id}/reindex")
async def admin_reindex_workspace(
    request: Request, workspace_id: str, body: WorkspaceIndexBody | None = None
) -> dict[str, Any]:
    """Start full/code/docs reindex for any workspace (admin)."""
    await require_admin(request)
    await get_current_user(request)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s
                """,
                (workspace_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from apps.backend.infrastructure import workspace_retrieval

    mode = (body.mode if body else "full").strip().lower()
    if mode not in ("full", "code", "docs"):
        mode = "full"
    max_files = body.max_files if body else 5000

    kick = workspace_retrieval.start_semantic_index_async(
        workspace_id, row[3], max_files=max_files, mode=mode
    )
    status = workspace_retrieval.index_status_payload(row)
    return {
        "ok": True,
        "workspace": workspace_row_to_api(row),
        "started": bool(kick.get("started")),
        "already_running": bool(kick.get("already_running")),
        "job": kick.get("job"),
        "status": status,
    }
