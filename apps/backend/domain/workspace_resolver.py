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
                from apps.backend.infrastructure.workspace_columns import (
                    WORKSPACE_SELECT_SQL,
                    workspace_row_to_api,
                )

                cur.execute(
                    f"""
                    SELECT {WORKSPACE_SELECT_SQL}
                    FROM project_workspaces
                    WHERE id = %s AND (owner_user_id = %s OR access_role IN ('editor', 'viewer'))
                    """,
                    (str(workspace_id), user.id),
                )
                row = cur.fetchone()

                if not row:
                    logger.debug("workspace not found or not accessible: %s", workspace_id)
                    return None

                api = workspace_row_to_api(row)
                return {
                    "type": "db",
                    "state": WorkspaceState.READY,
                    "source": api["source"],
                    "git_url": api.get("git_url"),
                    "git_branch": api.get("git_branch"),
                    "path": api["path"],
                    "repo_path": api["path"],
                    "name": api["name"],
                    "id": api["id"],
                    "owner_user_id": api["owner_user_id"],
                    "access_role": api["access_role"],
                    "verify_command": api.get("verify_command"),
                    "verify_required": bool(api.get("verify_required", False)),
                    "mcp_stdio_servers": api.get("mcp_stdio_servers"),
                    "semantic_index_enabled": api.get("semantic_index_enabled", True),
                    "retrieval_enabled": api.get("retrieval_enabled", True),
                    "last_index_at": api.get("last_index_at"),
                    "last_index_stats": api.get("last_index_stats"),
                    "last_index_error": api.get("last_index_error"),
                    "docs_rag_enabled": api.get("docs_rag_enabled", True),
                    "last_docs_rag_at": api.get("last_docs_rag_at"),
                    "last_docs_rag_stats": api.get("last_docs_rag_stats"),
                    "last_docs_rag_error": api.get("last_docs_rag_error"),
                    "index_on_write": api.get("index_on_write"),
                    "graph_index_enabled": api.get("graph_index_enabled", True),
                    "retrieve_context_sources": api.get("retrieve_context_sources"),
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