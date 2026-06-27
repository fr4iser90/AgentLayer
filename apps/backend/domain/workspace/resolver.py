"""Workspace Resolver - only reads/decides, no mutations."""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class WorkspaceResolverDependencies(Protocol):
    def resolve_db_workspace(self, workspace_id: str, user: Any) -> dict[str, Any] | None: ...


_deps: WorkspaceResolverDependencies | None = None


def register_workspace_resolver_dependencies(deps: WorkspaceResolverDependencies) -> None:
    global _deps
    _deps = deps


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
    - source, path, repo_path, name, id, ...

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
    if _deps is not None:
        return _deps.resolve_db_workspace(workspace_id, user)
    logger.debug("workspace resolver dependencies not registered")
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
        if source == "manual":
            return {
                "type": "local",
                "path": workspace.get("path"),
            }

    return {"type": "unknown", "path": None}


def is_workspace_ready(workspace: dict[str, Any]) -> bool:
    """Check if workspace is in READY state."""
    return workspace.get("state") == WorkspaceState.READY
