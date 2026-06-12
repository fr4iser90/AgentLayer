"""Workspace Service - handles mutations (create, clone, cleanup).

AgentLayer self-workspace follows ADR 0005: DB row ``name = agentlayer-self``, UUID as
``workspace_id``, rw tree under ``AGENTLAYER_WORKSPACE_PATH/{user_id}/agentlayer-self``.
Magic ``__agentlayer_self__`` is accepted only as a legacy alias in ``ensure_workspace``.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENTLAYER_SELF_NAME = "agentlayer-self"
_WORKSPACE_NAME_MAX_LEN = 255


def validate_workspace_name(name: str) -> str:
    """
    Return a stripped workspace name safe for use as a single path segment under
    ``AGENTLAYER_WORKSPACE_PATH/{user_id}/``.

    Raises :class:`WorkspaceCreateError` on empty, reserved, or traversal-like names.
    """
    nm = (name or "").strip()
    if not nm:
        raise WorkspaceCreateError("name is required")
    if len(nm) > _WORKSPACE_NAME_MAX_LEN:
        raise WorkspaceCreateError(
            f"workspace name must be at most {_WORKSPACE_NAME_MAX_LEN} characters"
        )
    if nm in (".", ".."):
        raise WorkspaceCreateError("invalid workspace name")
    if "\0" in nm or "/" in nm or "\\" in nm:
        raise WorkspaceCreateError("workspace name must not contain path separators")
    return nm


def resolve_user_workspace_dir(base: Path, user_id: Any, name: str) -> Path:
    """Resolve the on-disk workspace directory; must remain under ``base / user_id``."""
    nm = validate_workspace_name(name)
    user_root = (base / str(user_id)).resolve()
    target = (user_root / nm).resolve()
    try:
        target.relative_to(user_root)
    except ValueError:
        raise WorkspaceCreateError("invalid workspace name") from None
    return target


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


def reset_agentlayer_self_workspace(
    user, *, backup_existing: bool = True
) -> dict[str, Any] | None:
    """
    Destructive reset of the user's ``agentlayer-self`` workspace contents.

    - Requires ``self_editing_allowed(user)``.
    - Optionally moves the existing directory to ``agentlayer-self.backup-<timestamp>`` before re-seeding.
    - Always re-seeds from the ADR 0005 seed directory (``/workspace/AgentLayer`` or ``/app`` with ``.git``).
    """
    if not self_editing_allowed(user):
        return None
    seed = _agentlayer_self_seed_dir()
    if seed is None:
        logger.error("agentlayer-self reset: no seed repo with .git under /workspace/AgentLayer or /app")
        return None

    from apps.backend.domain.workspace_resolver import resolve_db_workspace
    from apps.backend.infrastructure.db import db

    target = self_workspace_target_path(user)
    expected = str(target)

    try:
        # Ensure DB row exists and path matches ADR.
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, path FROM project_workspaces WHERE owner_user_id = %s AND name = %s",
                    (user.id, AGENTLAYER_SELF_NAME),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """
                        INSERT INTO project_workspaces
                        (owner_user_id, name, path, source, git_url, git_branch, access_role)
                        VALUES (%s, %s, %s, 'manual', NULL, 'main', 'owner')
                        RETURNING id
                        """,
                        (user.id, AGENTLAYER_SELF_NAME, expected),
                    )
                    row = cur.fetchone()
                else:
                    wid, stored_path = row[0], str(row[1])
                    if stored_path != expected:
                        logger.info(
                            "agentlayer-self reset: updating DB path %s -> %s for id=%s",
                            stored_path,
                            expected,
                            wid,
                        )
                        cur.execute(
                            "UPDATE project_workspaces SET path = %s WHERE id = %s",
                            (expected, wid),
                        )
            conn.commit()

        if not row:
            return None
        wid = str(row[0])

        # Rotate existing directory.
        if target.exists():
            if backup_existing:
                ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
                backup = target.with_name(f"{target.name}.backup-{ts}")
                logger.warning("agentlayer-self reset: moving %s -> %s", target, backup)
                if backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
                shutil.move(str(target), str(backup))
            else:
                logger.warning("agentlayer-self reset: deleting %s", target)
                shutil.rmtree(target, ignore_errors=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        logger.warning("agentlayer-self reset: copying seed %s -> %s", seed, target)
        shutil.copytree(seed, target)

        return resolve_db_workspace(wid, user)
    except Exception as e:
        logger.exception("reset_agentlayer_self_workspace: %s", e)
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
                    SELECT id, name, path, source, git_url, git_branch, verify_command, verify_required
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
                    "verify_command": row[6],
                    "verify_required": bool(row[7]) if row[7] is not None else False,
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


def _sanitize_implementation_branch_slug(raw: str | None) -> str:
    t = re.sub(r"[^a-zA-Z0-9._-]+", "-", (raw or "").strip())[:40].strip("-_.")
    return t or uuid.uuid4().hex[:8]


def _git_run(repo: Path, args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo.resolve()), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def create_implementation_git_branch(
    user,
    workspace_id: str,
    *,
    base_branch: str | None = None,
    implementation_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Create ``agent/impl-<slug>`` at the resolved base ref, then ``git checkout`` it.

    Owner/editor only. Requires a git checkout under the workspace path. Does not fetch remotes.
    """
    from apps.backend.infrastructure.db import db

    wid = str(workspace_id).strip()
    if not wid:
        return {"ok": False, "error": "workspace_id is required"}

    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT path, name, git_branch, source
                    FROM project_workspaces
                    WHERE id = %s AND owner_user_id = %s AND access_role IN ('owner', 'editor')
                    """,
                    (wid, user.id),
                )
                row = cur.fetchone()
    except Exception as e:
        logger.exception("create_implementation_git_branch: db: %s", e)
        return {"ok": False, "error": "database error"}

    if not row:
        return {"ok": False, "error": "workspace not found or no permission to modify"}

    repo_path = Path(str(row[0])).resolve()
    ws_name = str(row[1] or "")
    default_base = (str(row[2] or "main").strip() or "main") if row[3] == "git" else "main"
    base = (base_branch or "").strip() or default_base

    if ws_name == AGENTLAYER_SELF_NAME and not self_editing_allowed(user):
        return {"ok": False, "error": "agentlayer-self workspace is not enabled for this user"}

    if not shutil.which("git"):
        return {"ok": False, "error": "git binary not found on server"}

    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return {"ok": False, "error": "workspace path is not a git repository (no .git)"}

    slug = _sanitize_implementation_branch_slug(implementation_run_id)
    new_branch = f"agent/impl-{slug}"

    show_ref = _git_run(repo_path, ["show-ref", "--verify", "--quiet", f"refs/heads/{new_branch}"])
    if show_ref.returncode == 0:
        return {
            "ok": False,
            "error": f"branch {new_branch!r} already exists; pick another implementation_run_id or delete the branch",
        }

    def _rev_ok(ref: str) -> tuple[str | None, str]:
        r = _git_run(repo_path, ["rev-parse", "--verify", f"{ref}^{{commit}}"])
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout.strip(), "")
        return (None, (r.stderr or r.stdout or "rev-parse failed").strip())

    start, err = _rev_ok(base)
    if not start:
        start, err2 = _rev_ok(f"origin/{base}")
        if not start:
            return {
                "ok": False,
                "error": f"could not resolve base branch {base!r} locally or as origin/{base}: {err or err2}",
            }

    br = _git_run(repo_path, ["branch", new_branch, start])
    if br.returncode != 0:
        msg = (br.stderr or br.stdout or "").strip() or "git branch failed"
        return {"ok": False, "error": msg[:2000]}

    co = _git_run(repo_path, ["checkout", new_branch])
    if co.returncode != 0:
        msg = (co.stderr or co.stdout or "").strip() or "git checkout failed"
        _git_run(repo_path, ["branch", "-D", new_branch])
        return {"ok": False, "error": msg[:2000]}

    log = _git_run(repo_path, ["log", "-1", "--oneline"])
    head_line = (log.stdout or "").strip()[:500]

    return {
        "ok": True,
        "branch": new_branch,
        "base_branch": base,
        "start_commit": start,
        "head_summary": head_line,
    }


class WorkspaceCreateError(Exception):
    """Raised when :func:`create_project_workspace_for_user` cannot complete (quota, clone, DB)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _workspace_base_path() -> Path:
    return Path(os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace"))


def slug_from_git_url(git_url: str) -> str:
    t = (git_url or "").strip().rstrip("/")
    if t.lower().endswith(".git"):
        t = t[:-4]
    seg = t.split("/")[-1] or "repo"
    seg = re.sub(r"[^a-zA-Z0-9_.-]+", "-", seg).strip("-_.")[:48]
    return seg or "repo"


def create_project_workspace_for_user(
    user,
    *,
    name: str,
    source: str,
    git_url: str | None = None,
    git_branch: str = "main",
    benchmark_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Create a row in ``project_workspaces`` and materialize on disk (same rules as ``POST /v1/workspaces``).

    Returns API-shaped workspace dict (``id``, ``name``, ``path``, …).
    Raises :class:`WorkspaceCreateError` on failure.
    """
    from apps.backend.domain.identity import get_benchmark_run_id
    from apps.backend.infrastructure.benchmark_resource_service import user_benchmark_workspace_quota
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

    br_ins = (git_branch or "main").strip() or "main"
    gu_ins = (git_url or "").strip() if src == "git" else None

    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO project_workspaces (
                      owner_user_id, name, path, source, git_url, git_branch, access_role, benchmark_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'owner', %s)
                    RETURNING id, owner_user_id, name, path, source, git_url, git_branch, access_role, created_at, updated_at,
                              verify_command, verify_required
                    """,
                    (user.id, nm, str(user_workspace_dir), src, gu_ins, br_ins, bench_run_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise WorkspaceCreateError("Failed to create workspace (no row returned)")
        return {
            "id": str(row[0]),
            "owner_user_id": str(row[1]),
            "name": row[2],
            "path": row[3],
            "source": row[4],
            "git_url": row[5],
            "git_branch": row[6],
            "access_role": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
            "verify_command": row[10],
            "verify_required": bool(row[11]) if row[11] is not None else False,
            "semantic_index_enabled": True,
            "retrieval_enabled": True,
            "last_index_at": None,
            "last_index_stats": None,
            "last_index_error": None,
        }
    except Exception as e:
        from psycopg.errors import UniqueViolation

        ex: BaseException | None = e
        while ex is not None and not isinstance(ex, UniqueViolation):
            ex = ex.__cause__ or ex.__context__
        shutil.rmtree(user_workspace_dir, ignore_errors=True)
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
        from apps.backend.infrastructure.code_index_qdrant import get_code_index

        get_code_index().delete_workspace(workspace_id)
    except Exception as e:
        logger.debug("qdrant delete_workspace skipped: %s", e)
    try:
        from apps.backend.infrastructure.code_graph_neo4j import get_code_graph

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
                    SELECT path, name FROM project_workspaces
                    WHERE id = %s AND owner_user_id = %s AND access_role = 'owner'
                    """,
                    (wid, owner_user_id),
                )
                row = cur.fetchone()
                if not row:
                    return False

                ws_path = Path(row[0])
                _delete_workspace_db_dependencies(cur, wid)
                cur.execute("DELETE FROM project_workspaces WHERE id = %s", (wid,))
            conn.commit()

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
