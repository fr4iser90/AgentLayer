"""Batch-ingest Markdown files into RAG (shared by HTTP admin route and startup bootstrap)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.embedding_client import (
    format_embedding_http_error,
    format_embedding_request_error,
)
import apps.backend.api.rag as rag_service

logger = logging.getLogger(__name__)

_STARTUP_RAG_DOMAIN = "agentlayer_docs"

_MAX_MARKDOWN_BYTES = 2_000_000
# ``apps/backend/domain/...`` → repository root (contains ``docs/``).
_DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"


def resolve_docs_root() -> Path:
    s = operator_settings.effective_docs_root_str()
    if s:
        return Path(s).expanduser().resolve()
    return _DEFAULT_DOCS_DIR.resolve()


def ingest_markdown_tree(
    tenant_id: int,
    user_id: uuid.UUID,
    docs_root: Path,
    domain: str,
    *,
    purge_first: bool,
) -> dict[str, object]:
    """
    Walk ``docs_root`` for ``*.md``, ingest each file. Returns the same shape as the HTTP handler.
    """
    domain = domain.strip()
    if not domain:
        raise ValueError("domain is required")

    if not docs_root.is_dir():
        raise FileNotFoundError(f"docs_root not found or not a directory: {docs_root}")

    try:
        rag_service.embed_one("agentlayer")
    except Exception as e:
        return {
            "ok": False,
            "domain": domain,
            "docs_root": str(docs_root),
            "purge_deleted_documents": 0,
            "files_ingested": 0,
            "chunk_count_total": 0,
            "files": [],
            "errors": [{"path": "(embed probe)", "error": str(e)}],
        }

    deleted_docs = 0
    if purge_first:
        deleted_docs = db.rag_delete_documents_by_tenant_domain(tenant_id, domain)

    files_ok: list[str] = []
    errors: list[dict[str, str]] = []
    total_chunks = 0

    paths = sorted(docs_root.rglob("*.md"))
    for path in paths:
        rel = path.relative_to(docs_root).as_posix()
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
            title = f"docs/{rel}"
            source_uri = f"agentlayer-docs:{rel}"
            out = rag_service.ingest_for_user(
                tenant_id,
                user_id,
                domain,
                title,
                text,
                source_uri,
            )
            total_chunks += int(out.get("chunk_count") or 0)
            files_ok.append(rel)
        except (OSError, UnicodeError) as e:
            errors.append({"path": rel, "error": str(e)})
        except ValueError as e:
            errors.append({"path": rel, "error": str(e)})
        except httpx.HTTPStatusError as e:
            logger.warning("ingest-docs embedding HTTP error path=%s: %s", rel, e)
            errors.append({"path": rel, "error": format_embedding_http_error(e)})
        except httpx.RequestError as e:
            logger.warning("ingest-docs embedding unreachable path=%s: %s", rel, e)
            errors.append({"path": rel, "error": format_embedding_request_error(e)})
        except Exception as e:
            logger.warning("ingest-docs failed path=%s: %s", rel, e)
            errors.append({"path": rel, "error": str(e)})

    return {
        "ok": len(errors) == 0,
        "domain": domain,
        "docs_root": str(docs_root),
        "purge_deleted_documents": deleted_docs,
        "files_ingested": len(files_ok),
        "chunk_count_total": total_chunks,
        "files": files_ok,
        "errors": errors,
    }


def run_startup_rag_docs_ingest() -> None:
    """
    Ingest ``docs/**/*.md`` at API process start when RAG is enabled.
    Uses the oldest admin user as document owner (``agentlayer_docs`` is tenant-wide for search).
    """
    logger.info("RAG docs startup ingest starting")
    if not operator_settings.rag_settings()["enabled"]:
        logger.info("RAG docs startup ingest skipped (rag disabled)")
        return
    admin_id = db.user_first_admin_id()
    if admin_id is None:
        logger.warning("RAG docs startup ingest skipped (no admin user yet)")
        return
    root = resolve_docs_root()
    if not root.is_dir():
        logger.warning("RAG docs startup ingest skipped (missing docs dir: %s)", root)
        return
    tenant_id = db.user_tenant_id(admin_id)
    try:
        summary = ingest_markdown_tree(
            tenant_id,
            admin_id,
            root,
            _STARTUP_RAG_DOMAIN,
            purge_first=True,
        )
    except Exception:
        logger.exception("RAG docs startup ingest aborted")
        return
    errs = summary.get("errors")
    if errs:
        if len(errs) == 1 and isinstance(errs[0], dict) and errs[0].get("path") == "(embed probe)":
            logger.warning(
                "RAG docs startup ingest skipped: %s",
                errs[0].get("error", errs),
            )
        else:
            logger.error("RAG docs startup ingest finished with errors: %s", errs)
    logger.info(
        "RAG docs startup ingest: domain=%s files=%s chunks=%s purge_deleted=%s",
        summary.get("domain"),
        summary.get("files_ingested"),
        summary.get("chunk_count_total"),
        summary.get("purge_deleted_documents"),
    )
