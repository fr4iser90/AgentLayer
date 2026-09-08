"""Project workspace creation and deletion services."""
from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from apps.backend.infrastructure.workspace.workspace_columns import (
    CLIENT_EXECUTION,
    SERVER_EXECUTION,
    WORKSPACE_SELECT_SQL,
    normalize_execution_mode,
    workspace_row_to_api,
)
from apps.backend.infrastructure.workspace.workspace_project_common import (
    AGENTLAYER_SELF_NAME,
    WorkspaceCreateError,
    WorkspaceState,
    resolve_user_workspace_dir,
    slug_from_git_url,
    validate_client_workspace_path,
    validate_workspace_name,
    workspace_base_path,
)

logger = logging.getLogger(__name__)


def _workspace_base_path() -> Path:
    return workspace_base_path()

def create_project_workspace_for_user(
    user,
    *,
    name: str,
    source: str,
    git_url: str | None = None,
    git_branch: str = "main",
    benchmark_run_id: uuid.UUID | None = None,
    execution_mode: str = SERVER_EXECUTION,
    path: str | None = None,
) -> dict[str, Any]:
    """
    Create a row in ``project_workspaces`` and materialize on disk (same rules as ``POST /v1/workspaces``).

    Returns API-shaped workspace dict (``id``, ``name``, ``path``, …).
    Raises :class:`WorkspaceCreateError` on failure.
    """
    from apps.backend.domain.shared.identity import get_benchmark_run_id
    from apps.backend.infrastructure.benchmarks.benchmark_resource_service import user_benchmark_workspace_quota
    from apps.backend.infrastructure.db import db

    bench_run_id = benchmark_run_id or get_benchmark_run_id()

    nm = validate_workspace_name(name)
    if nm == AGENTLAYER_SELF_NAME:
        raise WorkspaceCreateError(
            "Reserved workspace name. Use the AgentLayer self workspace when self-editing is enabled."
        )

    src = (source or "manual").strip().lower()
    if src not in ("manual", "git"):
        raise WorkspaceCreateError("source must be manual or git")
    if src == "git" and not (git_url or "").strip():
        raise WorkspaceCreateError("git_url is required when source is git")

    mode = normalize_execution_mode(execution_mode)
    from apps.backend.infrastructure.platform.client_surface_policy import (
        refuse_api_key_workspace_mode,
        refuse_server_workspace_for_user,
    )

    mode_refuse = refuse_api_key_workspace_mode(mode)
    if mode_refuse:
        raise WorkspaceCreateError(mode_refuse)
    admin_refuse = refuse_server_workspace_for_user(user, mode)
    if admin_refuse:
        raise WorkspaceCreateError(admin_refuse)
    if mode == CLIENT_EXECUTION and src == "git":
        raise WorkspaceCreateError(
            "A client workspace cannot be git-cloned on the server. "
            "Clone it locally, then create with execution_mode=client and the local path."
        )

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            if bench_run_id is not None:
                bench_quota = user_benchmark_workspace_quota(user.id)
                cur.execute(
                    """
                    SELECT COUNT(*) FROM project_workspaces
                    WHERE owner_user_id = %s AND benchmark_run_id IS NOT NULL
                    """,
                    (user.id,),
                )
                bench_count = int((cur.fetchone() or [0])[0] or 0)
                if bench_count >= bench_quota:
                    raise WorkspaceCreateError(
                        f"Benchmark workspace quota exceeded ({bench_quota} max). "
                        "Clean benchmark sandboxes in Admin → Benchmarks."
                    )
            else:
                cur.execute(
                    "SELECT COALESCE(workspace_quota, 10) FROM users WHERE id = %s",
                    (user.id,),
                )
                row = cur.fetchone()
                quota = int(row[0] if row else 10)
                cur.execute(
                    """
                    SELECT COUNT(*) FROM project_workspaces
                    WHERE owner_user_id = %s AND benchmark_run_id IS NULL
                    """,
                    (user.id,),
                )
                existing_count = int((cur.fetchone() or [0])[0] or 0)
                if existing_count >= quota:
                    raise WorkspaceCreateError(
                        f"Workspace quota exceeded ({quota} max). Delete some workspaces first."
                    )

    materialized_dir: Path | None = None
    if mode == CLIENT_EXECUTION:
        stored_path = validate_client_workspace_path(path)
    else:
        base = _workspace_base_path()
        user_workspace_dir = resolve_user_workspace_dir(base, user.id, nm)
        if src == "git":
            gu = git_url.strip()
            user_workspace_dir.parent.mkdir(parents=True, exist_ok=True)
            if user_workspace_dir.exists():
                shutil.rmtree(user_workspace_dir, ignore_errors=True)
            user_workspace_dir.mkdir(parents=True, exist_ok=True)
            br = (git_branch or "main").strip() or "main"
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--branch",
                    br,
                    "--depth",
                    "1",
                    gu,
                    str(user_workspace_dir),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                shutil.rmtree(user_workspace_dir, ignore_errors=True)
                err = (result.stderr or result.stdout or "").strip() or "git clone failed"
                raise WorkspaceCreateError(f"Git clone failed: {err[:800]}")
        else:
            user_workspace_dir.mkdir(parents=True, exist_ok=True)
        stored_path = str(user_workspace_dir)
        materialized_dir = user_workspace_dir

    br_ins = (git_branch or "main").strip() or "main"
    gu_ins = (git_url or "").strip() if src == "git" else None

    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        INDEX_CONSENT_NONE,
        INDEX_CONSENT_TEXT,
        clamp_index_consent,
    )

    index_consent = INDEX_CONSENT_NONE if mode == CLIENT_EXECUTION else clamp_index_consent(INDEX_CONSENT_TEXT)

    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO project_workspaces (
                      owner_user_id, name, path, source, git_url, git_branch,
                      access_role, benchmark_run_id, execution_mode, index_consent
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'owner', %s, %s, %s)
                    RETURNING id
                    """,
                    (user.id, nm, stored_path, src, gu_ins, br_ins, bench_run_id, mode, index_consent),
                )
                created = cur.fetchone()
                if not created:
                    raise WorkspaceCreateError("Failed to create workspace (no row returned)")
                cur.execute(
                    "SELECT " + WORKSPACE_SELECT_SQL + " FROM project_workspaces WHERE id = %s",
                    (created[0],),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise WorkspaceCreateError("Failed to create workspace (no row returned)")
        return workspace_row_to_api(row)
    except Exception as e:
        from psycopg.errors import UniqueViolation

        ex: BaseException | None = e
        while ex is not None and not isinstance(ex, UniqueViolation):
            ex = ex.__cause__ or ex.__context__
        if materialized_dir is not None:
            shutil.rmtree(materialized_dir, ignore_errors=True)
        if isinstance(ex, UniqueViolation):
            raise WorkspaceCreateError(
                "Workspace name already exists for this user; pick a different name."
            ) from e
        raise WorkspaceCreateError(str(e)[:800]) from e


def _delete_workspace_db_dependencies(cur: Any, workspace_id: str) -> None:
    """
    Remove rows that block ``DELETE FROM project_workspaces``.

    ``agent_tasks`` with ``scope='workspace'`` cannot have ``workspace_id`` set to NULL
    (check constraint) when the FK fires — delete them explicitly first.
    """
    cur.execute("DELETE FROM agent_tasks WHERE workspace_id = %s", (workspace_id,))


def _delete_workspace_files(ws_path: Path) -> None:
    if not ws_path.exists():
        return
    shutil.rmtree(ws_path, ignore_errors=False)


def _delete_workspace_index_sidecars(workspace_id: str) -> None:
    """Best-effort Qdrant / Neo4j cleanup (non-fatal)."""
    try:
        from apps.backend.infrastructure.codebase.code_index_qdrant import get_code_index

        get_code_index().delete_workspace(workspace_id)
    except Exception as e:
        logger.debug("qdrant delete_workspace skipped: %s", e)
    try:
        from apps.backend.infrastructure.codebase.code_graph_neo4j import get_code_graph

        get_code_graph().delete_workspace(workspace_id)
    except Exception as e:
        logger.debug("neo4j delete_workspace skipped: %s", e)


def delete_owned_workspace(*, workspace_id: str, owner_user_id: Any) -> bool:
    """
    Delete DB row + on-disk tree for a workspace owned by ``owner_user_id``.
    Returns False when not found / not owner.
    """
    from apps.backend.infrastructure.db import db

    wid = str(workspace_id).strip()
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT path, name, execution_mode FROM project_workspaces
                    WHERE id = %s AND owner_user_id = %s AND access_role = 'owner'
                    """,
                    (wid, owner_user_id),
                )
                row = cur.fetchone()
                if not row:
                    return False

                ws_path = Path(row[0])
                client_side = normalize_execution_mode(row[2]) == CLIENT_EXECUTION
                _delete_workspace_db_dependencies(cur, wid)
                cur.execute("DELETE FROM project_workspaces WHERE id = %s", (wid,))
            conn.commit()

        # The stored path for a client workspace belongs to the user's machine. Deleting
        # it here would walk whatever happens to exist at that path in the container.
        if not client_side:
            _delete_workspace_files(ws_path)
        _delete_workspace_index_sidecars(wid)
        logger.info("deleted workspace %s (%s)", wid, row[1])
        return True
    except Exception as e:
        logger.error("failed to delete workspace %s: %s", wid, e)
        raise


def cleanup_workspace(workspace_id: str, user) -> bool:
    """Clean up workspace (delete files, optionally remove DB entry)."""
    try:
        return delete_owned_workspace(workspace_id=workspace_id, owner_user_id=user.id)
    except Exception as e:
        logger.error("failed to cleanup workspace: %s", e)
        return False
