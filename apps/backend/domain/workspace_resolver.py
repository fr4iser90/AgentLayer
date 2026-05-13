"""Workspace Resolver - only reads/decides, no mutations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceState:
    """Workspace lifecycle states."""
    CREATED = "created"
    CLONING = "cloning"
    READY = "ready"
    ERROR = "error"


def resolve_workspace(workspace_id: str | None, user) -> dict[str, Any] | None:
    """
    Resolve workspace by ID from ``project_workspaces``.

    Returns workspace dict with:
    - type: ``db``
    - state: CREATED/CLONING/READY/ERROR
    - source, path, repo_path, name, id, …

    AgentLayer self-workspace (``agentlayer-self``) uses the same shape; use
    ``workspace_service.ensure_workspace`` (including legacy ``__agentlayer_self__`` alias).

    Returns None if workspace not found or not ready.
    """
    if not workspace_id:
        logger.debug("no workspace_id provided")
        return None

    # ``__agentlayer_self__`` is handled only in ``workspace_service.ensure_workspace`` (ADR 0005).
    return resolve_db_workspace(workspace_id, user)


def resolve_db_workspace(workspace_id: str, user) -> dict[str, Any] | None:
    """Resolve workspace from database."""
    from apps.backend.infrastructure.db import db
    
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, path, source, git_url, git_branch, access_role, owner_user_id
                    FROM project_workspaces 
                    WHERE id = %s AND (owner_user_id = %s OR access_role IN ('editor', 'viewer'))
                    """,
                    (str(workspace_id), user.id),
                )
                row = cur.fetchone()
                
                if not row:
                    logger.debug("workspace not found or not accessible: %s", workspace_id)
                    return None
                
                return {
                    "type": "db",
                    "state": WorkspaceState.READY,
                    "source": row[3],  # source: manual/git
                    "git_url": row[4],
                    "git_branch": row[5],
                    "path": row[2],  # path from DB
                    "repo_path": row[2],
                    "name": row[1],
                    "id": str(row[0]),
                    "owner_user_id": str(row[7]),
                    "access_role": row[6],
                }
    except Exception as e:
        logger.error("failed to resolve workspace from DB: %s", e)
        return None


def resolve_source(workspace: dict[str, Any]) -> dict[str, Any]:
    """
    Determine source for workspace (local/remote).
    
    Returns source config with:
    - type: "local" or "remote"
    - path: source path or URL
    """
    ws_type = workspace.get("type")

    if ws_type == "db":
        source = workspace.get("source")
        if source == "git" and workspace.get("git_url"):
            return {
                "type": "remote",
                "path": workspace.get("git_url"),
                "branch": workspace.get("git_branch", "main"),
            }
        elif source == "manual":
            return {
                "type": "local",
                "path": workspace.get("path"),
            }
    
    return {"type": "unknown", "path": None}


def is_workspace_ready(workspace: dict[str, Any]) -> bool:
    """Check if workspace is in READY state."""
    return workspace.get("state") == WorkspaceState.READY