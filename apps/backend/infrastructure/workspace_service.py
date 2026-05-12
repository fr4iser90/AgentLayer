"""Workspace Service - handles mutations (create, clone, cleanup)."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceState:
    """Workspace lifecycle states."""
    CREATED = "created"
    CLONING = "cloning"
    READY = "ready"
    ERROR = "error"


def ensure_workspace(workspace_id: str, user) -> dict[str, Any] | None:
    """
    Ensure workspace exists and is READY.
    
    1. Resolve workspace (may return existing)
    2. If not ready, create/clone
    3. Return workspace dict
    """
    from apps.backend.domain.workspace_resolver import (
        resolve_workspace,
        WorkspaceState,
    )
    
    # Try to resolve existing workspace
    workspace = resolve_workspace(workspace_id, user)
    
    if workspace and workspace.get("state") == WorkspaceState.READY:
        logger.debug("workspace already ready: %s", workspace_id)
        return workspace
    
    # Need to create/clone
    if workspace_id == "__agentlayer_self__":
        workspace = create_self_workspace(user)
    else:
        workspace = create_db_workspace(workspace_id, user)
    
    return workspace


def create_self_workspace(user) -> dict[str, Any] | None:
    """
    Create self-workspace (AgentLayer self-editing).
    
    Self-workspace is a COPY of the mounted local repo.
    """
    from apps.backend.infrastructure.db import db
    
    logger.info("creating self-workspace for user %s", user.id)
    
    # Get base workspace path
    base_path = os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace")
    user_workspace_dir = Path(base_path) / str(user.id) / "agentlayer-self"
    
    # Check if already exists
    if user_workspace_dir.exists():
        logger.info("self-workspace already exists: %s", user_workspace_dir)
    else:
        # Copy from mounted local repo
        source_path = Path("/workspace/AgentLayer")
        if not source_path.exists():
            logger.error("source path does not exist: %s", source_path)
            return None
        
        logger.info("copying local repo to %s", user_workspace_dir)
        try:
            user_workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            # Use shutil.copytree for complete copy (not git clone!)
            shutil.copytree(source_path, user_workspace_dir)
            logger.info("copy complete")
        except Exception as e:
            logger.error("failed to copy repo: %s", e)
            return None
    
    # Ensure DB entry exists
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                # Check if entry exists
                cur.execute(
                    "SELECT id FROM project_workspaces WHERE owner_user_id = %s AND name = %s",
                    (user.id, "agentlayer-self"),
                )
                row = cur.fetchone()
                
                if not row:
                    # Create DB entry
                    cur.execute(
                        """
                        INSERT INTO project_workspaces (owner_user_id, name, path, source, access_role)
                        VALUES (%s, %s, %s, 'manual', 'editor')
                        RETURNING id
                        """,
                        (user.id, "agentlayer-self", str(user_workspace_dir)),
                    )
                    row = cur.fetchone()
                conn.commit()
    except Exception as e:
        logger.error("failed to ensure DB entry: %s", e)
    
    return {
        "type": "self",
        "state": WorkspaceState.READY,
        "source": "local",
        "path": str(user_workspace_dir),
        "repo_path": str(user_workspace_dir),
        "name": "AgentLayer (self)",
        "id": "__agentlayer_self__",
    }


def create_db_workspace(workspace_id: str, user) -> dict[str, Any] | None:
    """
    Create workspace from DB entry.
    
    For git workspaces, clone the repo.
    For manual workspaces, ensure directory exists.
    """
    from apps.backend.infrastructure.db import db
    
    logger.info("creating DB workspace: %s", workspace_id)
    
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, path, source, git_url, git_branch
                    FROM project_workspaces 
                    WHERE id = %s AND (owner_user_id = %s OR access_role IN ('editor', 'viewer'))
                    """,
                    (str(workspace_id), user.id),
                )
                row = cur.fetchone()
                
                if not row:
                    logger.warning("workspace not found: %s", workspace_id)
                    return None
                
                ws_path = Path(row[2])
                ws_source = row[3]
                ws_git_url = row[4]
                ws_branch = row[5] or "main"
                
                # Ensure directory exists
                if not ws_path.exists():
                    ws_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    if ws_source == "git" and ws_git_url:
                        # Clone git repo
                        logger.info("cloning git repo: %s", ws_git_url)
                        import subprocess
                        result = subprocess.run(
                            ["git", "clone", "--depth", "1", "--branch", ws_branch, ws_git_url, str(ws_path)],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode != 0:
                            logger.error("git clone failed: %s", result.stderr)
                            return None
                    else:
                        # Create empty directory
                        ws_path.mkdir(parents=True)
                
                return {
                    "type": "db",
                    "state": WorkspaceState.READY,
                    "source": ws_source,
                    "path": str(ws_path),
                    "repo_path": str(ws_path),
                    "name": row[1],
                    "id": str(row[0]),
                    "git_url": ws_git_url,
                    "git_branch": ws_branch,
                }
    except Exception as e:
        logger.error("failed to create workspace: %s", e)
        return None


def checkout_branch(workspace: dict[str, Any], branch: str) -> bool:
    """Checkout a branch in the workspace repo."""
    repo_path = workspace.get("repo_path")
    if not repo_path:
        logger.error("no repo_path in workspace")
        return False
    
    try:
        import subprocess
        result = subprocess.run(
            ["git", "checkout", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("git checkout failed: %s", result.stderr)
            return False
        return True
    except Exception as e:
        logger.error("failed to checkout branch: %s", e)
        return False


def cleanup_workspace(workspace_id: str, user) -> bool:
    """Clean up workspace (delete files, optionally remove DB entry)."""
    from apps.backend.infrastructure.db import db
    
    # Only allow cleanup for user's own workspaces
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT path FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
                    (str(workspace_id), user.id),
                )
                row = cur.fetchone()
                
                if not row:
                    logger.warning("cannot cleanup: workspace not owned by user")
                    return False
                
                ws_path = Path(row[0])
                
                # Delete files
                if ws_path.exists():
                    shutil.rmtree(ws_path)
                    logger.info("deleted workspace files: %s", ws_path)
                
                # Remove DB entry
                cur.execute(
                    "DELETE FROM project_workspaces WHERE id = %s",
                    (str(workspace_id),),
                )
                conn.commit()
                
                return True
    except Exception as e:
        logger.error("failed to cleanup workspace: %s", e)
        return False