"""HTTP API for project workspaces (/v1/workspaces)."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.core.config import config
from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api
from apps.backend.infrastructure import workspace_retrieval

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

# Read-only HTTP browse: max bytes returned for a single file (text-ish).
_WORKSPACE_FS_READ_MAX_BYTES = 512_000


def _get_workspace_base_path() -> Path:
    base = os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace")
    return Path(base)


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


class WorkspaceIndexBody(BaseModel):
    max_files: int = Field(default=5000, ge=100, le=20000)


class ImplementationBranchBody(BaseModel):
    """Create ``agent/impl-<slug>`` from a resolvable base ref (local or ``origin/<name>``)."""

    base_branch: str | None = Field(default=None, max_length=255)
    implementation_run_id: str | None = Field(default=None, max_length=128)


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
    return workspace_row_to_api(row)


def _get_self_workspace(user) -> dict[str, Any] | None:
    """List/API shape for agentlayer-self (ADR 0005); ``None`` if disabled or seed missing."""
    from apps.backend.infrastructure.workspace_service import ensure_workspace, self_editing_allowed

    if not self_editing_allowed(user):
        return None
    ws_int = ensure_workspace("__agentlayer_self__", user)
    if not ws_int:
        return None
    wid = ws_int.get("id")
    if not wid:
        return None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s
                """,
                (wid, user.id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_workspace(row)


@router.get("")
async def list_workspaces(request: Request):
    """List all workspaces for the current user, including built-in AgentLayer workspace if enabled."""
    user = await get_current_user(request)
    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE owner_user_id = %s
                ORDER BY name ASC
                """,
                (user.id,),
            )
            rows = cur.fetchall()

    workspaces = [_row_to_workspace(r) for r in rows]
    if not self_editing_allowed(user):
        workspaces = [w for w in workspaces if (w.get("name") or "").strip() != AGENTLAYER_SELF_NAME]

    self_ws = _get_self_workspace(user)
    if self_ws:
        existing_ids = {ws.get("id") for ws in workspaces}
        if self_ws.get("id") not in existing_ids:
            workspaces.insert(0, self_ws)

    return {"workspaces": workspaces}


from apps.backend.infrastructure.workspace_service import (
    WorkspaceCreateError,
    create_project_workspace_for_user,
)


@router.post("")
async def create_workspace(request: Request, body: WorkspaceCreateBody):
    """Create a new workspace (manual folder or git clone)."""
    user = await get_current_user(request)
    try:
        ws = create_project_workspace_for_user(
            user,
            name=body.name,
            source=body.source,
            git_url=body.git_url,
            git_branch=body.git_branch or "main",
        )
    except WorkspaceCreateError as e:
        raise HTTPException(status_code=400, detail=e.message)
    return {"workspace": ws}


@router.get("/{workspace_id}")
async def get_workspace(request: Request, workspace_id: str):
    """Get a specific workspace."""
    user = await get_current_user(request)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s
                """,
                (workspace_id, user.id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    if (row[2] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {"workspace": _row_to_workspace(row)}


@router.get("/{workspace_id}/index/status")
async def workspace_index_status(request: Request, workspace_id: str) -> dict[str, Any]:
    """Semantic index / retrieval layer status for this workspace."""
    user = await get_current_user(request)
    row = workspace_retrieval.fetch_workspace_row_shared(workspace_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    if (row[2] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace_retrieval.index_status_payload(row)


@router.post("/{workspace_id}/index")
async def workspace_run_index(
    request: Request, workspace_id: str, body: WorkspaceIndexBody | None = None
) -> dict[str, Any]:
    """Build or refresh the Qdrant symbol index for this workspace."""
    user = await get_current_user(request)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s AND access_role IN ('owner', 'editor')
                """,
                (workspace_id, user.id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    if (row[2] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    sem, _ret = workspace_retrieval._row_flags(row)
    if not sem:
        raise HTTPException(status_code=400, detail="semantic_index_enabled is off for this workspace")

    max_files = body.max_files if body else 5000
    kick = workspace_retrieval.start_semantic_index_async(workspace_id, row[3], max_files=max_files)
    status = workspace_retrieval.index_status_payload(
        workspace_retrieval.fetch_workspace_row(workspace_id, user.id)
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
    from apps.backend.infrastructure.workspace_git import (
        workspace_git_changes_summary,
        workspace_git_file_diff,
    )

    root_disk, _row = await _workspace_root_path_row(request, workspace_id)
    summary = workspace_git_changes_summary(root_disk)
    if not summary.get("is_git_repo"):
        raise HTTPException(status_code=400, detail=str(summary.get("error") or "not a git repository"))
    if path and str(path).strip():
        file_diff = workspace_git_file_diff(root_disk, path)
        if not file_diff.get("ok") and file_diff.get("error"):
            raise HTTPException(status_code=400, detail=str(file_diff.get("error")))
        return {**summary, **{k: file_diff[k] for k in ("path", "diff", "diff_truncated") if k in file_diff}}
    return summary


@router.post("/{workspace_id}/git/implementation-branch")
async def create_implementation_branch(request: Request, workspace_id: str, body: ImplementationBranchBody):
    """Create ``agent/impl-<slug>`` from a local (or ``origin/<name>``) base ref; then check it out."""
    user = await get_current_user(request)
    from apps.backend.infrastructure.workspace_service import create_implementation_git_branch

    result = create_implementation_git_branch(
        user,
        workspace_id,
        base_branch=body.base_branch,
        implementation_run_id=body.implementation_run_id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "branch creation failed"))
    return result


@router.patch("/{workspace_id}")
async def update_workspace(request: Request, workspace_id: str, body: WorkspaceUpdateBody):
    """Update workspace (rename, change branch)."""
    user = await get_current_user(request)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s AND access_role IN ('owner', 'editor')
                """,
                (workspace_id, user.id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    if (row[2] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no edit permission")

    updates = []
    params = []

    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
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
        from apps.backend.infrastructure.mcp_runtime import _parse_servers_payload

        mcp_val = patch["mcp_stdio_servers"]
        if mcp_val is None or mcp_val == []:
            updates.append("mcp_stdio_servers_json = NULL")
        else:
            if not isinstance(mcp_val, list):
                raise HTTPException(status_code=400, detail="mcp_stdio_servers must be a JSON array or null")
            try:
                _parse_servers_payload(mcp_val)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            updates.append("mcp_stdio_servers_json = %s::jsonb")
            params.append(json.dumps(mcp_val))
    if "semantic_index_enabled" in patch and patch["semantic_index_enabled"] is not None:
        updates.append("semantic_index_enabled = %s")
        params.append(bool(patch["semantic_index_enabled"]))
    if "retrieval_enabled" in patch and patch["retrieval_enabled"] is not None:
        updates.append("retrieval_enabled = %s")
        params.append(bool(patch["retrieval_enabled"]))

    if updates:
        params.append(workspace_id)
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE project_workspaces SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s",
                    tuple(params),
                )
            conn.commit()

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces WHERE id = %s
                """,
                (workspace_id,),
            )
            row = cur.fetchone()

    return {"workspace": _row_to_workspace(row)}


@router.delete("/{workspace_id}")
async def delete_workspace(request: Request, workspace_id: str):
    """Delete a workspace (owner only)."""
    user = await get_current_user(request)

    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT path, name FROM project_workspaces WHERE id = %s AND owner_user_id = %s AND access_role = 'owner'",
                (workspace_id, user.id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or no delete permission")

    if (row[1] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found or no delete permission")

    workspace_path = Path(row[0])
    if workspace_path.exists():
        shutil.rmtree(workspace_path)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project_workspaces WHERE id = %s", (workspace_id,))
        conn.commit()

    return {"ok": True}


@router.get("/{workspace_id}/validate-path")
async def validate_workspace_path(request: Request, workspace_id: str):
    """Check if workspace path exists and is accessible."""
    user = await get_current_user(request)

    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT path, name FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
                (workspace_id, user.id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[1] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_path = Path(row[0])
    return {
        "exists": workspace_path.exists(),
        "path": str(workspace_path),
        "is_directory": workspace_path.is_dir() if workspace_path.exists() else False,
    }


async def _workspace_root_path_row(request: Request, workspace_id: str) -> tuple[Path, tuple]:
    """Filesystem root path and DB row (path, name) for workspace owned by user."""
    user = await get_current_user(request)
    from apps.backend.infrastructure.workspace_service import AGENTLAYER_SELF_NAME, self_editing_allowed

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT path, name FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
                (workspace_id, user.id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[1] or "").strip() == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        raise HTTPException(status_code=404, detail="Workspace not found")

    return Path(row[0]), row


def _looks_textish(blob: bytes) -> bool:
    return b"\x00" not in blob[:8192]


@router.get("/{workspace_id}/fs/list")
async def workspace_fs_list(
    request: Request,
    workspace_id: str,
    path: str = Query("", max_length=4096, description="Directory path relative to workspace root"),
):
    """List files and subdirectories (read-only; same caps as coding_list_dir)."""
    root_disk, _row = await _workspace_root_path_row(request, workspace_id)
    try:
        target = safe_resolve_under_workspace(root_disk, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path") from None

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    rel_base = ""
    try:
        rel_base = str(target.relative_to(root_disk.resolve())).replace("\\", "/")
    except ValueError:
        rel_base = ""

    max_entries = config.WORKSPACE_MAX_LIST_ENTRIES
    entries: list[dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(target)):
            if name in (".", ".."):
                continue
            fp = target / name
            try:
                is_dir = fp.is_dir()
                is_link = fp.is_symlink()
            except OSError:
                continue
            rel_child = f"{rel_base}/{name}".strip("/") if rel_base else name
            entries.append(
                {
                    "name": name,
                    "path": rel_child.replace("\\", "/"),
                    "is_dir": is_dir,
                    "is_symlink": is_link,
                }
            )
            if len(entries) >= max_entries:
                break
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "ok": True,
        "path": rel_base or ".",
        "entries": entries,
        "truncated": len(entries) >= max_entries,
        "max_entries": max_entries,
    }


@router.get("/{workspace_id}/fs/read")
async def workspace_fs_read(
    request: Request,
    workspace_id: str,
    path: str = Query(..., min_length=1, max_length=4096, description="File path relative to workspace root"),
):
    """Read a text-ish file from the workspace (read-only, size-capped)."""
    root_disk, _row = await _workspace_root_path_row(request, workspace_id)
    try:
        target = safe_resolve_under_workspace(root_disk, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path") from None

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        size = target.stat().st_size
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if size > _WORKSPACE_FS_READ_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large for preview (max {_WORKSPACE_FS_READ_MAX_BYTES} bytes)",
        )

    try:
        blob = target.read_bytes()
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not _looks_textish(blob):
        raise HTTPException(status_code=415, detail="Binary file — preview not supported")

    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = blob.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=415, detail="Could not decode file as text") from None

    rel = str(target.relative_to(root_disk.resolve())).replace("\\", "/")
    return {"ok": True, "path": rel, "content": text, "size": size}