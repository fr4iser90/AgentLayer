"""Workspace path validation and read-only filesystem browse endpoints."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.workspace.use_cases import workspace_controller_services as ws_services

router = APIRouter()
_WORKSPACE_FS_READ_MAX_BYTES = 512_000


def safe_resolve_under_workspace(root: Path, rel: str | None) -> Path:
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

@router.get("/{workspace_id}/validate-path")
async def validate_workspace_path(request: Request, workspace_id: str):
    """Check if workspace path exists and is accessible."""
    user = await get_current_user(request)
    row = ws_services.fetch_owned_workspace_path_name(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[1] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
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
    row = ws_services.fetch_owned_workspace_path_name(workspace_id, user.id)

    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if (row[1] or "").strip() == ws_services.AGENTLAYER_SELF_NAME and not ws_services.self_editing_allowed(user):
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

    max_entries = ws_services.config.WORKSPACE_MAX_LIST_ENTRIES
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
