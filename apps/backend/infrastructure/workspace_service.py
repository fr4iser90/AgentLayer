"""Workspace Service - handles mutations (create, clone, cleanup).

AgentLayer self-workspace follows ADR 0005: DB row ``name = agentlayer-self``, UUID as
``workspace_id``, rw tree under ``AGENTLAYER_WORKSPACE_PATH/{user_id}/agentlayer-self``.
Magic ``__agentlayer_self__`` is accepted only as a legacy alias in ``ensure_workspace``.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENTLAYER_SELF_NAME = "agentlayer-self"


class WorkspaceState:
    """Workspace lifecycle states."""

    CREATED = "created"
    CLONING = "cloning"
    READY = "ready"
    ERROR = "error"


def _agentlayer_self_seed_dir() -> Path | None:
    """ADR 0005: first directory that is a git checkout — ``/workspace/AgentLayer``, else ``/app``."""
    for p in (Path("/workspace/AgentLayer"), Path("/app")):
        if p.is_dir() and (p / ".git").is_dir():
            return p
    return None


def self_editing_allowed(user) -> bool:
    """Operator flag + (admin or ``workspace_self_allowed``)."""
    from apps.backend.infrastructure.operator_settings import public_dict
    from apps.backend.infrastructure.db import db

    try:
        if not public_dict().get("workspace_allow_self_editing", False):
            return False
    except Exception:
        logger.warning("failed to read operator settings for self-workspace")
        return False
    if getattr(user, "role", None) == "admin":
        return True
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(workspace_self_allowed, false) FROM users WHERE id = %s",
                    (user.id,),
                )
                row = cur.fetchone()
                return bool(row and row[0])
    except Exception as e:
        logger.warning("failed to check workspace_self_allowed: %s", e)
        return False


def self_workspace_target_path(user) -> Path:
    base = Path(os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace"))
    return base / str(user.id) / AGENTLAYER_SELF_NAME


def try_resolve_agentlayer_self_db(user) -> dict[str, Any] | None:
    """If DB row exists and on-disk path matches ADR tree, return same shape as ``resolve_db_workspace``."""
    if not self_editing_allowed(user):
        return None
    from apps.backend.domain.workspace_resolver import resolve_db_workspace
    from apps.backend.infrastructure.db import db

    expected = str(self_workspace_target_path(user))
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, path FROM project_workspaces
                    WHERE owner_user_id = %s AND name = %s
                    """,
                    (user.id, AGENTLAYER_SELF_NAME),
                )
                row = cur.fetchone()
        if not row:
            return None
        wid, stored_path = str(row[0]), str(row[1])
        if stored_path != expected:
            logger.info(
                "agentlayer-self: DB path %s != expected %s — will rematerialize",
                stored_path,
                expected,
            )
            return None
        ws = resolve_db_workspace(wid, user)
        if not ws:
            return None
        if not Path(ws["path"]).exists():
            return None
        return ws
    except Exception as e:
        logger.warning("try_resolve_agentlayer_self_db: %s", e)
        return None


def materialize_agentlayer_self_workspace(user) -> dict[str, Any] | None:
    """Create rw copy from seed + ensure DB row; return ``resolve_db_workspace`` dict or None."""
    if not self_editing_allowed(user):
        logger.debug("materialize_agentlayer_self: not allowed for user %s", user.id)
        return None
    seed = _agentlayer_self_seed_dir()
    if seed is None:
        logger.error(
            "agentlayer-self: no seed repo with .git under /workspace/AgentLayer or /app"
        )
        return None

    target = self_workspace_target_path(user)
    from apps.backend.domain.workspace_resolver import resolve_db_workspace
    from apps.backend.infrastructure.db import db

    try:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            logger.info("agentlayer-self: copying seed %s -> %s", seed, target)
            shutil.copytree(seed, target)
        else:
            logger.debug("agentlayer-self: target already exists %s", target)

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, path FROM project_workspaces WHERE owner_user_id = %s AND name = %s",
                    (user.id, AGENTLAYER_SELF_NAME),
                )
                row = cur.fetchone()
                if row:
                    wid, stored_path = row[0], str(row[1])
                    if stored_path != str(target):
                        logger.info(
                            "agentlayer-self: updating path %s -> %s for id=%s",
                            stored_path,
                            target,
                            wid,
                        )
                        cur.execute(
                            "UPDATE project_workspaces SET path = %s WHERE id = %s",
                            (str(target), wid),
                        )
                if not row:
                    cur.execute(
                        """
                        INSERT INTO project_workspaces
                        (owner_user_id, name, path, source, git_url, git_branch, access_role)
                        VALUES (%s, %s, %s, 'manual', NULL, 'main', 'owner')
                        RETURNING id
                        """,
                        (user.id, AGENTLAYER_SELF_NAME, str(target)),
                    )
                    row = cur.fetchone()
            conn.commit()
        if not row:
            return None
        return resolve_db_workspace(str(row[0]), user)
    except Exception as e:
        logger.exception("materialize_agentlayer_self_workspace: %s", e)
        return None


def ensure_workspace(workspace_id: str, user) -> dict[str, Any] | None:
    """
    Ensure workspace exists and is READY.

    1. Resolve workspace (may return existing)
    2. If not ready, create/clone
    3. Return workspace dict
    """
    from apps.backend.domain.workspace_resolver import WorkspaceState, resolve_workspace

    if workspace_id == "__agentlayer_self__":
        if not self_editing_allowed(user):
            return None
        ws = try_resolve_agentlayer_self_db(user)
        if ws and ws.get("state") == WorkspaceState.READY:
            return ws
        return materialize_agentlayer_self_workspace(user)

    workspace = resolve_workspace(workspace_id, user)

    if workspace and workspace.get("state") == WorkspaceState.READY:
        if workspace.get("name") == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
            logger.debug("agentlayer-self: denied for user %s (uuid resolve)", getattr(user, "id", None))
            return None
        logger.debug("workspace already ready: %s", workspace_id)
        return workspace

    return create_db_workspace(workspace_id, user)


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
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                "--branch",
                                ws_branch,
                                ws_git_url,
                                str(ws_path),
                            ],
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
