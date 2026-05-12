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
    Resolve workspace by ID.
    
    Returns workspace dict with:
    - type: "self" or "db"
    - state: CREATED/CLONING/READY/ERROR
    - source: "local" or "remote" or None
    - path: absolute filesystem path
    - repo_path: path to git repo (if applicable)
    
    Returns None if workspace not found or not ready.
    """
    if not workspace_id:
        logger.debug("no workspace_id provided")
        return None
    
    # Check for self-workspace special ID
    if workspace_id == "__agentlayer_self__":
        return resolve_self_workspace(user)
    
    # Resolve from DB
    return resolve_db_workspace(workspace_id, user)


def resolve_self_workspace(user) -> dict[str, Any] | None:
    """
    Resolve AgentLayer self-workspace.
    
    Self-workspace comes from local mount, not DB entry.
    """
    from apps.backend.infrastructure.operator_settings import public_dict
    from apps.backend.infrastructure.db import db
    
    # Check if self-editing is allowed
    try:
        settings = public_dict()
        if not settings.get("workspace_allow_self_editing", False):
            logger.debug("self-editing not allowed in operator settings")
            return None
    except Exception:
        logger.warning("failed to check operator settings")
        return None
    
    # Check if user can access self-workspace
    if user.role != "admin":
        try:
            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(workspace_self_allowed, false) FROM users WHERE id = %s",
                        (user.id,),
                    )
                    row = cur.fetchone()
                    if not row or not row[0]:
                        logger.debug("user %s not allowed for self-workspace", user.id)
                        return None
        except Exception as e:
            logger.warning("failed to check user self-workspace permission: %s", e)
            return None
    
    # Self-workspace uses the mounted directory directly
    workspace_path = Path("/workspace/AgentLayer")
    if not workspace_path.exists():
        logger.warning("self-workspace mount not found: %s", workspace_path)
        return None
    
    return {
        "type": "self",
        "state": WorkspaceState.READY,
        "source": "local",
        "path": str(workspace_path),
        "repo_path": str(workspace_path / "repo"),
        "name": "AgentLayer (self)",
        "id": "__agentlayer_self__",
    }


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
    
    if ws_type == "self":
        # Self uses local mount
        return {
            "type": "local",
            "path": workspace.get("path"),
        }
    
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