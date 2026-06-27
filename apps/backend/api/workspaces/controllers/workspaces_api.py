"""HTTP API for project workspaces (/v1/workspaces)."""

from __future__ import annotations

import logging
from pathlib import Path
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.workspace.use_cases import workspace_controller_services as ws_services

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

# Read-only HTTP browse: max bytes returned for a single file (text-ish).
_WORKSPACE_FS_READ_MAX_BYTES = 512_000


def _get_workspace_base_path() -> Path:
    return ws_services.workspace_base_path()


logger = logging.getLogger(__name__)


class WorkspaceCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source: str = Field(default="manual", max_length=32)
    git_url: str | None = None
    git_branch: str = Field(default="main", max_length=255)


class WorkspaceUpdateBody(BaseModel):
    name: str | None = None
    git_branch: str | None = None
    verify_command: str | None = None
    verify_required: bool | None = None
    mcp_stdio_servers: list[dict[str, Any]] | None = None
    semantic_index_enabled: bool | None = None
    retrieval_enabled: bool | None = None
    docs_rag_enabled: bool | None = None
    index_on_write: str | None = Field(
        default=None,
        description="off | debounced | immediate | null = operator default",
    )
    graph_index_enabled: bool | None = None
    retrieve_context_sources: list[str] | None = None


class WorkspaceIndexBody(BaseModel):
    max_files: int = Field(default=5000, ge=100, le=20000)
    mode: str = Field(
        default="full",
        description="full: code (Qdrant+Neo4j) + workspace docs RAG; code: symbols+graph only; docs: *.md RAG only",
    )


class ImplementationBranchBody(BaseModel):
    """Create ``agent/impl-<slug>`` from a resolvable base ref (local or ``origin/<name>``)."""

    base_branch: str | None = Field(default=None, max_length=255)
    implementation_run_id: str | None = Field(default=None, max_length=128)


class WorkspaceSelfResetBody(BaseModel):
    backup_existing: bool = Field(
        default=True,
        description="When true, move existing agentlayer-self directory to a timestamped backup before re-seeding.",
    )


def safe_resolve_under_workspace(root: Path, rel: str | None) -> Path:
    """Resolve ``rel`` under ``root``; reject absolute paths and escapes after ``resolve()``."""
    root_r = root.resolve()
    r = (rel or "").strip().replace("\\", "/")
    if r in ("", "."):
        return root_r
    if r.startswith("/"):
        raise ValueError("invalid path")
    target = (root_r / r).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        raise ValueError("path outside workspace") from None
    return target


def _row_to_workspace(row: tuple) -> dict[str, Any]:
    return ws_services.row_to_workspace(row)


def _get_self_workspace(user) -> dict[str, Any] | None:
    """List/API shape for agentlayer-self (ADR 0005); ``None`` if disabled or seed missing."""
    if not ws_services.self_editing_allowed(user):
        return None
    ws_int = ws_services.ensure_workspace("__agentlayer_self__", user)
    if not ws_int:
        return None
    wid = ws_int.get("id")
    if not wid:
        return None
    row = ws_services.fetch_owned_workspace_row(str(wid), user.id)
    if not row:
        return None
    return _row_to_workspace(row)


@router.get("")
async def list_workspaces(request: Request):
    """List all workspaces for the current user, including built-in AgentLayer workspace if enabled."""
    user = await get_current_user(request)
    rows = ws_services.fetch_owned_workspace_rows(user.id)

    workspaces = [_row_to_workspace(r) for r in rows]
    if not ws_services.self_editing_allowed(user):
        workspaces = [
            w for w in workspaces if (w.get("name") or "").strip() != ws_services.AGENTLAYER_SELF_NAME
        ]

    self_ws = _get_self_workspace(user)
    if self_ws:
        existing_ids = {ws.get("id") for ws in workspaces}
        if self_ws.get("id") not in existing_ids:
            workspaces.insert(0, self_ws)

    return {"workspaces": workspaces}

@router.post("")
async def create_workspace(request: Request, body: WorkspaceCreateBody):
    """Create a new workspace (manual folder or git clone)."""
    user = await get_current_user(request)
    try:
        ws = ws_services.create_project_workspace_for_user(
            user,
            name=body.name,
            source=body.source,
            git_url=body.git_url,
            git_branch=body.git_branch or "main",
        )
    except ws_services.WorkspaceCreateError as e:
        raise HTTPException(status_code=400, detail=e.message)
    return {"workspace": ws}


@router.get("/{workspace_id}")
async def get_workspace(request: Request, workspace_id: str):
    """Get a specific workspace."""
    user = await get_current_user(request)

    row = ws_services.fetch_owned_workspace_row(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[2] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {"workspace": _row_to_workspace(row)}


@router.get("/{workspace_id}/index/status")
async def workspace_index_status(request: Request, workspace_id: str) -> dict[str, Any]:
    """Semantic index / retrieval layer status for this workspace."""
    user = await get_current_user(request)
    row = ws_services.workspace_retrieval.fetch_workspace_row_shared(workspace_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if (row[2] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws_services.workspace_retrieval.index_status_payload(row)


@router.post("/{workspace_id}/index")
async def workspace_run_index(
    request: Request, workspace_id: str, body: WorkspaceIndexBody | None = None
) -> dict[str, Any]:
    """Build or refresh code index (Qdrant + Neo4j) and/or workspace docs RAG."""
    user = await get_current_user(request)
    row = ws_services.fetch_editable_workspace_row(workspace_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    if (row[2] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    sem, _ret, docs_rag = ws_services.workspace_retrieval._row_flags(row)
    mode = (body.mode if body else "full").strip().lower()
    if mode not in ("full", "code", "docs"):
        mode = "full"

    if mode in ("full", "code") and not sem:
        raise HTTPException(status_code=400, detail="semantic_index_enabled is off for this workspace")
    if mode == "docs" and not docs_rag:
        raise HTTPException(status_code=400, detail="docs_rag_enabled is off for this workspace")

    max_files = body.max_files if body else 5000
    kick = ws_services.workspace_retrieval.start_semantic_index_async(
        workspace_id, row[3], max_files=max_files, mode=mode
    )
    status = ws_services.workspace_retrieval.index_status_payload(
        ws_services.workspace_retrieval.fetch_workspace_row(workspace_id, user.id)
    )
    return {
        "ok": True,
        "started": bool(kick.get("started")),
        "already_running": bool(kick.get("already_running")),
        "job": kick.get("job"),
        "status": status,
    }


@router.get("/{workspace_id}/git/changes")
async def workspace_git_changes(
    request: Request,
    workspace_id: str,
    path: str | None = Query(
        default=None,
        max_length=4096,
        description="Optional relative file path; when set, response includes unified diff for that file",
    ),
):
    """Read-only working-tree change summary (``git status`` / ``diff --stat``) and optional per-file diff."""
    user = await get_current_user(request)
    row = ws_services.fetch_owned_workspace_path_name(workspace_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if (row[1] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")
    root_disk = Path(row[0])
    summary = ws_services.workspace_git_changes_summary(root_disk)
    if not summary.get("is_git_repo"):
        raise HTTPException(status_code=400, detail=str(summary.get("error") or "not a git repository"))
    if path and str(path).strip():
        file_diff = ws_services.workspace_git_file_diff(root_disk, path)
        if not file_diff.get("ok") and file_diff.get("error"):
            raise HTTPException(status_code=400, detail=str(file_diff.get("error")))
        return {**summary, **{k: file_diff[k] for k in ("path", "diff", "diff_truncated") if k in file_diff}}
    return summary


@router.post("/{workspace_id}/git/implementation-branch")
async def create_implementation_branch(request: Request, workspace_id: str, body: ImplementationBranchBody):
    """Create ``agent/impl-<slug>`` from a local (or ``origin/<name>``) base ref; then check it out."""
    user = await get_current_user(request)

    result = ws_services.create_implementation_git_branch(
        user,
        workspace_id,
        base_branch=body.base_branch,
        implementation_run_id=body.implementation_run_id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "branch creation failed"))
    return result


@router.post("/{workspace_id}/self/reset")
async def reset_self_workspace(request: Request, workspace_id: str, body: WorkspaceSelfResetBody | None = None):
    """Destructive reset/re-seed for the AgentLayer self workspace (ADR 0005)."""
    user = await get_current_user(request)
    row = ws_services.fetch_editable_workspace_row(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    if (row[2] or "").strip() != ws_services.AGENTLAYER_SELF_NAME:
        raise HTTPException(status_code=400, detail="Reset is only supported for agentlayer-self")
    if not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    backup_existing = bool(body.backup_existing) if body is not None else True
    ws = ws_services.reset_agentlayer_self_workspace(user, backup_existing=backup_existing)
    if not ws:
        raise HTTPException(status_code=500, detail="Failed to reset agentlayer-self (seed missing or server error)")

    # Return fresh DB-shaped record.
    row2 = ws_services.fetch_owned_workspace_row(workspace_id, user.id)
    if not row2:
        raise HTTPException(status_code=500, detail="Workspace reset but could not read DB row")
    return {"ok": True, "workspace": _row_to_workspace(row2)}


@router.patch("/{workspace_id}")
async def update_workspace(request: Request, workspace_id: str, body: WorkspaceUpdateBody):
    """Update workspace (rename, change branch)."""
    user = await get_current_user(request)
    row = ws_services.fetch_editable_workspace_row(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    if (row[2] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    updates = []
    params = []

    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        try:
            patch["name"] = ws_services.validate_workspace_name(patch["name"])
        except ws_services.WorkspaceCreateError as e:
            raise HTTPException(status_code=400, detail=e.message) from e
        if patch["name"] == ws_services.AGENTLAYER_SELF_NAME:
            raise HTTPException(
                status_code=400,
                detail="Reserved workspace name. Use the AgentLayer self workspace when self-editing is enabled.",
            )
        updates.append("name = %s")
        params.append(patch["name"])
    if "git_branch" in patch and patch["git_branch"] is not None:
        updates.append("git_branch = %s")
        params.append(patch["git_branch"])
    if "verify_command" in patch:
        updates.append("verify_command = %s")
        params.append(patch["verify_command"])
    if "verify_required" in patch and patch["verify_required"] is not None:
        updates.append("verify_required = %s")
        params.append(bool(patch["verify_required"]))
    if "mcp_stdio_servers" in patch:
        mcp_val = patch["mcp_stdio_servers"]
        if mcp_val is None or mcp_val == []:
            updates.append("mcp_stdio_servers_json = NULL")
        else:
            if not isinstance(mcp_val, list):
                raise HTTPException(status_code=400, detail="mcp_stdio_servers must be a JSON array or null")
            try:
                ws_services._parse_servers_payload(mcp_val)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            updates.append("mcp_stdio_servers_json = %s::jsonb")
            params.append(ws_services.encode_jsonb(mcp_val))
    if "semantic_index_enabled" in patch and patch["semantic_index_enabled"] is not None:
        updates.append("semantic_index_enabled = %s")
        params.append(bool(patch["semantic_index_enabled"]))
    if "retrieval_enabled" in patch and patch["retrieval_enabled"] is not None:
        updates.append("retrieval_enabled = %s")
        params.append(bool(patch["retrieval_enabled"]))
    if "docs_rag_enabled" in patch and patch["docs_rag_enabled"] is not None:
        updates.append("docs_rag_enabled = %s")
        params.append(bool(patch["docs_rag_enabled"]))
    if "index_on_write" in patch:
        v = patch["index_on_write"]
        if v is None or (isinstance(v, str) and not str(v).strip()):
            updates.append("index_on_write = NULL")
        else:
            norm = ws_services.normalize_index_on_write(v)
            if norm is None:
                raise HTTPException(
                    status_code=400,
                    detail="index_on_write must be off, debounced, immediate, or null",
                )
            updates.append("index_on_write = %s")
            params.append(norm)
    if "graph_index_enabled" in patch and patch["graph_index_enabled"] is not None:
        updates.append("graph_index_enabled = %s")
        params.append(bool(patch["graph_index_enabled"]))
    if "retrieve_context_sources" in patch:
        src = patch["retrieve_context_sources"]
        if src is None or src == []:
            updates.append("retrieve_context_sources = NULL")
        else:
            parsed = ws_services.parse_retrieve_context_sources(src)
            if not parsed:
                raise HTTPException(status_code=400, detail="retrieve_context_sources invalid")
            updates.append("retrieve_context_sources = %s::jsonb")
            params.append(ws_services.encode_jsonb(parsed))

    if updates:
        ws_services.update_workspace_row(workspace_id, updates, params)

    row = ws_services.fetch_owned_workspace_row(workspace_id, user.id)

    return {"workspace": _row_to_workspace(row)}


@router.delete("/{workspace_id}")
async def delete_workspace(request: Request, workspace_id: str):
    """Delete a workspace (owner only)."""
    user = await get_current_user(request)
    row = ws_services.fetch_owned_delete_workspace_name(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no delete permission")

    if (row[0] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no delete permission")

    try:
        if not ws_services.delete_owned_workspace(workspace_id=workspace_id, owner_user_id=user.id):
            raise HTTPException(status_code=404, detail="Workspace not found or no delete permission")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_workspace failed for %s", workspace_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete workspace: {e!s}"[:500],
        ) from e

    return {"ok": True}

from apps.backend.api.workspaces.controllers.workspaces_delegate_api import router as delegate_router
from apps.backend.api.workspaces.controllers.workspaces_files_api import router as files_router

router.include_router(files_router)
router.include_router(delegate_router)
