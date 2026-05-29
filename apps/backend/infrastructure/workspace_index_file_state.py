"""Per-file index fingerprints for workspace stale detection."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".pytest_cache", ".mypy_cache", ".tox"}
)
_SUPPORTED_SUFFIXES = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs"}
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()


def iter_indexable_rel_paths(root: Path, *, max_files: int = 20000) -> list[str]:
    root_r = root.resolve()
    if not root_r.is_dir():
        return []
    out: list[str] = []
    for fp in root_r.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        skip = False
        for part in fp.parts:
            if part.startswith(".") or part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue
        try:
            rel = str(fp.relative_to(root_r)).replace("\\", "/")
        except ValueError:
            continue
        out.append(rel)
        if len(out) >= max_files:
            break
    return out


def upsert_file_states(workspace_id: str, entries: list[tuple[str, str]]) -> None:
    """``entries``: list of (relative_path, content_sha256)."""
    if not entries:
        return
    from apps.backend.infrastructure.db import db

    now = datetime.now(UTC)
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                for path, sha in entries:
                    if not path or not sha:
                        continue
                    cur.execute(
                        """
                        INSERT INTO workspace_index_file_state
                          (workspace_id, path, content_sha256, indexed_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (workspace_id, path) DO UPDATE SET
                          content_sha256 = EXCLUDED.content_sha256,
                          indexed_at = EXCLUDED.indexed_at
                        """,
                        (workspace_id, path, sha, now),
                    )
            conn.commit()
    except Exception as e:
        logger.warning("upsert_file_states failed: %s", e)


def delete_file_state(workspace_id: str, rel_path: str) -> None:
    from apps.backend.infrastructure.db import db

    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM workspace_index_file_state WHERE workspace_id = %s AND path = %s",
                    (workspace_id, rel),
                )
            conn.commit()
    except Exception as e:
        logger.warning("delete_file_state failed: %s", e)


def count_files_out_of_date(workspace_id: str, root: Path, *, max_check: int = 5000) -> int:
    """Files whose on-disk sha256 differs from last indexed state (or never indexed)."""
    from apps.backend.infrastructure.db import db

    paths = iter_indexable_rel_paths(root, max_files=max_check)
    if not paths:
        return 0
    stored: dict[str, str] = {}
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT path, content_sha256 FROM workspace_index_file_state
                    WHERE workspace_id = %s
                    """,
                    (workspace_id,),
                )
                for row in cur.fetchall():
                    stored[str(row[0])] = str(row[1])
    except Exception as e:
        logger.debug("count_files_out_of_date db: %s", e)
        return 0

    stale = 0
    root_r = root.resolve()
    for rel in paths:
        fp = root_r / rel
        if not fp.is_file():
            if rel in stored:
                stale += 1
            continue
        sha = file_sha256(fp)
        if not sha:
            continue
        if stored.get(rel) != sha:
            stale += 1
    return stale


def stale_summary(workspace_id: str, root: Path) -> dict[str, Any]:
    n = count_files_out_of_date(workspace_id, root)
    return {"files_out_of_date": n, "stale_by_files": n > 0}
