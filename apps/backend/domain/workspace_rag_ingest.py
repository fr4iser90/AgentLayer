"""Ingest Markdown from a project workspace into pgvector (workspace-scoped RAG)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db
import apps.backend.api.rag as rag_service

logger = logging.getLogger(__name__)

WORKSPACE_RAG_DOMAIN = "workspace_docs"
_MAX_MARKDOWN_BYTES = 2_000_000
_MAX_MARKDOWN_FILES = 500
_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".pytest_cache", ".mypy_cache", ".tox"}
)


def ingest_workspace_markdown_tree(
    workspace_id: uuid.UUID,
    docs_root: Path,
    *,
    purge_first: bool = True,
    max_files: int = _MAX_MARKDOWN_FILES,
) -> dict[str, object]:
    """
    Walk ``docs_root`` for ``*.md`` and ingest each file scoped to ``workspace_id``.
    """
    if not operator_settings.rag_settings()["enabled"]:
        return {"ok": False, "error": "rag_disabled", "files_ingested": 0, "chunk_count_total": 0}

    root = docs_root.resolve()
    if not root.is_dir():
        return {"ok": False, "error": "docs_root not a directory", "files_ingested": 0, "chunk_count_total": 0}

    tenant_id, user_id = get_identity()
    if user_id is None:
        return {"ok": False, "error": "no user identity", "files_ingested": 0, "chunk_count_total": 0}

    try:
        rag_service.embed_one("workspace rag probe")
    except Exception as e:
        return {
            "ok": False,
            "workspace_id": str(workspace_id),
            "files_ingested": 0,
            "chunk_count_total": 0,
            "errors": [{"path": "(embed probe)", "error": str(e)}],
        }

    deleted_docs = 0
    if purge_first:
        deleted_docs = db.rag_delete_documents_by_workspace(tenant_id, workspace_id)

    files_ok: list[str] = []
    errors: list[dict[str, str]] = []
    total_chunks = 0
    max_files = max(1, min(int(max_files), _MAX_MARKDOWN_FILES))

    paths: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.relative_to(root).parts):
            continue
        paths.append(path)
        if len(paths) >= max_files:
            break

    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            st = path.stat()
            if st.st_size > _MAX_MARKDOWN_BYTES:
                errors.append(
                    {"path": rel, "error": f"file too large (>{_MAX_MARKDOWN_BYTES} bytes)"}
                )
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            title = rel
            source_uri = f"workspace:{workspace_id}:{rel}"
            out = rag_service.ingest_for_user(
                tenant_id,
                user_id,
                WORKSPACE_RAG_DOMAIN,
                title,
                text,
                source_uri,
                workspace_id=workspace_id,
            )
            total_chunks += int(out.get("chunk_count") or 0)
            files_ok.append(rel)
        except (OSError, UnicodeError) as e:
            errors.append({"path": rel, "error": str(e)})
        except ValueError as e:
            errors.append({"path": rel, "error": str(e)})
        except httpx.HTTPStatusError as e:
            logger.warning("workspace rag ingest HTTP error path=%s: %s", rel, e)
            errors.append({"path": rel, "error": f"embedding HTTP: {e!s}"})
        except httpx.RequestError as e:
            errors.append({"path": rel, "error": f"embedding unreachable: {e!s}"})
        except Exception as e:
            logger.warning("workspace rag ingest failed path=%s: %s", rel, e)
            errors.append({"path": rel, "error": str(e)})

    return {
        "ok": len(errors) == 0,
        "workspace_id": str(workspace_id),
        "domain": WORKSPACE_RAG_DOMAIN,
        "docs_root": str(root),
        "purge_deleted_documents": deleted_docs,
        "files_ingested": len(files_ok),
        "chunk_count_total": total_chunks,
        "files": files_ok,
        "errors": errors,
    }
