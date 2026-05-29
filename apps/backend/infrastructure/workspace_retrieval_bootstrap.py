"""Session bootstrap text and index staleness for coding workspaces."""

from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MARKER = "[Workspace retrieval]"
_SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".pytest_cache"}
)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        s = ts.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def git_head_commit_time(root: Path) -> datetime | None:
    """Latest commit timestamp for ``root`` (if a git repo)."""
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip()
        return _parse_iso(line)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("git_head_commit_time: %s", e)
        return None


def is_index_stale(workspace: dict[str, Any]) -> bool:
    """True when never indexed, git HEAD newer than index, or indexed files differ on disk."""
    if workspace.get("semantic_index_enabled") is False:
        return False
    last_at = _parse_iso(workspace.get("last_index_at"))
    path = workspace.get("path") or workspace.get("repo_path")
    root: Path | None = Path(path) if isinstance(path, str) and path.strip() else None

    if last_at is None:
        return True

    if root and root.is_dir():
        try:
            from apps.backend.infrastructure.workspace_index_file_state import count_files_out_of_date

            wid = str(workspace.get("id") or "").strip()
            if wid and count_files_out_of_date(wid, root) > 0:
                return True
        except Exception:
            pass

    if root is None:
        return False
    head_at = git_head_commit_time(root)
    if head_at is None:
        return False
    return head_at > last_at


def list_repo_top_level(root: Path, *, limit: int = 18) -> list[str]:
    if not root.is_dir():
        return []
    names: list[str] = []
    try:
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith(".") or entry.name in _SKIP_DIR_NAMES:
                continue
            suffix = "/" if entry.is_dir() else ""
            names.append(entry.name + suffix)
            if len(names) >= limit:
                break
    except OSError as e:
        logger.debug("list_repo_top_level: %s", e)
    return names


def index_stale_reason(workspace: dict[str, Any]) -> str | None:
    if not is_index_stale(workspace):
        return None
    if not workspace.get("last_index_at"):
        return "never_indexed"
    path = workspace.get("path") or workspace.get("repo_path")
    if isinstance(path, str) and path.strip():
        try:
            from apps.backend.infrastructure.workspace_index_file_state import count_files_out_of_date

            wid = str(workspace.get("id") or "").strip()
            if wid and count_files_out_of_date(wid, Path(path)) > 0:
                return "files_changed_since_index"
        except Exception:
            pass
    return "git_head_newer_than_index"


def build_retrieval_bootstrap_snippet(workspace: dict[str, Any]) -> str:
    """Short system snippet: index state, tree, retrieval hints."""
    if not workspace or not isinstance(workspace, dict):
        return ""
    path_s = workspace.get("path") or workspace.get("repo_path")
    root = Path(path_s) if isinstance(path_s, str) and path_s.strip() else None

    lines: list[str] = [_MARKER]
    name = (workspace.get("name") or "workspace").strip()
    lines.append(f"Workspace: **{name}**")

    sem_on = workspace.get("semantic_index_enabled", True) is not False
    ret_on = workspace.get("retrieval_enabled", True) is not False
    lines.append(f"Semantic index: {'on' if sem_on else 'off'} · Retrieval: {'on' if ret_on else 'off'}")

    stats = workspace.get("last_index_stats")
    sym = stats.get("total_symbols") if isinstance(stats, dict) else None
    last_at = workspace.get("last_index_at")
    if last_at:
        sym_s = f", {sym} symbols" if isinstance(sym, int) else ""
        lines.append(f"Last index: {last_at}{sym_s}")
    elif sem_on:
        lines.append("Last index: never — run Reindex in the UI or `coding_index` before semantic search.")

    stale = index_stale_reason(workspace)
    if stale == "git_head_newer_than_index":
        lines.append("Index may be **stale** (commits after last index) — prefer Reindex for semantic queries.")
    elif stale == "files_changed_since_index":
        lines.append(
            "Index may be **stale** (files changed since last index) — Reindex or wait for background incremental index."
        )
    elif stale == "never_indexed" and sem_on:
        lines.append("No semantic index yet — use `coding_search` / grep; run index for Qdrant symbol search.")

    if root and root.is_dir():
        top = list_repo_top_level(root)
        if top:
            lines.append("Top-level: " + ", ".join(top))

    if ret_on:
        lines.append(
            "For unfamiliar code or docs, call **`retrieve_context`** first (grep + semantic + RAG); "
            "then `coding_read_file` on cited path:line."
        )

    return "\n".join(lines)


def maybe_schedule_index_on_attach(workspace: dict[str, Any]) -> bool:
    """Background reindex when operator flag is on and index is stale. Returns True if started."""
    from apps.backend.core.config import config

    if not config.AGENT_WORKSPACE_INDEX_ON_ATTACH:
        return False
    if not config.CODING_ENABLED:
        return False
    if workspace.get("semantic_index_enabled") is False:
        return False
    role = (workspace.get("access_role") or "owner").lower()
    if role not in ("owner", "editor"):
        return False
    if not is_index_stale(workspace):
        return False
    wid = str(workspace.get("id") or "").strip()
    path = workspace.get("path") or workspace.get("repo_path")
    if not wid or not isinstance(path, str) or not path.strip():
        return False
    try:
        from apps.backend.infrastructure.workspace_retrieval import (
            index_job_for_status,
            start_semantic_index_async,
        )

        job = index_job_for_status(wid)
        if job and job.get("status") == "running":
            return False
        start_semantic_index_async(wid, path)
        logger.info("index-on-attach: started background index for workspace %s", wid)
        return True
    except Exception as e:
        logger.warning("index-on-attach failed for %s: %s", wid, e)
        return False
