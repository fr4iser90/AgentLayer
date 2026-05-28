"""Shared incremental RAG markdown ingest (content hash + ingest fingerprint)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from apps.backend.api.rag import embed_one, ingest_for_user
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.embedding_client import (
    format_embedding_http_error,
    format_embedding_request_error,
)

logger = logging.getLogger(__name__)


def compute_rag_ingest_fingerprint() -> str:
    """Changes when embedding model/dim or chunking would invalidate stored vectors."""
    rs = operator_settings.rag_settings()
    payload = "|".join(
        [
            (rs.get("embedding_model") or "").strip(),
            str(int(rs.get("embedding_dim") or 0)),
            str(int(rs.get("chunk_size") or 0)),
            str(int(rs.get("chunk_overlap") or 0)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_config_changed(stored_fingerprint: str | None) -> bool:
    current = compute_rag_ingest_fingerprint()
    stored = (stored_fingerprint or "").strip()
    return not stored or stored != current


def ingest_markdown_paths(
    tenant_id: int,
    user_id: uuid.UUID,
    docs_root: Path,
    domain: str,
    paths: list[Path],
    *,
    source_uri_for_rel: Any,
    title_for_rel: Any,
    purge_first: bool = False,
    incremental: bool = True,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """
    Ingest a list of markdown paths under ``docs_root``.

    ``source_uri_for_rel`` / ``title_for_rel`` are callables ``(rel_posix: str) -> str``.
    """
    domain = domain.strip()
    if not domain:
        raise ValueError("domain is required")

    if not docs_root.is_dir():
        raise FileNotFoundError(f"docs_root not found or not a directory: {docs_root}")

    try:
        embed_one("ingest probe")
    except Exception as e:
        return _empty_summary(
            domain,
            docs_root,
            errors=[{"path": "(embed probe)", "error": str(e)}],
        )

    stored_fp = operator_settings.rag_docs_ingest_fingerprint()
    config_changed = ingest_config_changed(stored_fp)

    deleted_docs = 0
    existing: dict[str, dict[str, Any]] = {}

    if purge_first:
        deleted_docs = db.rag_delete_documents_by_tenant_domain(tenant_id, domain)
        incremental = False
    elif config_changed:
        logger.info(
            "RAG ingest: embedding/chunk config changed (fingerprint); re-embedding all documents in domain %r",
            domain,
        )
        deleted_docs = db.rag_delete_documents_by_tenant_domain(tenant_id, domain)
        incremental = False
    elif incremental:
        existing = db.rag_documents_by_tenant_domain_index(
            tenant_id, domain, workspace_id=workspace_id
        )

    files_ok: list[str] = []
    files_skipped: list[str] = []
    errors: list[dict[str, str]] = []
    total_chunks = 0
    seen_uris: set[str] = set()

    for path in paths:
        rel = path.relative_to(docs_root).as_posix()
        source_uri = source_uri_for_rel(rel)
        seen_uris.add(source_uri)
        try:
            st = path.stat()
            if st.st_size > 2_000_000:
                errors.append({"path": rel, "error": "file too large (>2000000 bytes)"})
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            content_hash = sha256_text(text)
            prev = existing.get(source_uri)
            if incremental and prev and (prev.get("content_sha256") or "") == content_hash:
                files_skipped.append(rel)
                continue
            if prev and prev.get("id") is not None:
                db.rag_delete_document_by_id(int(prev["id"]))
            title = title_for_rel(rel)
            out = ingest_for_user(
                tenant_id,
                user_id,
                domain,
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
            logger.warning("RAG ingest embedding HTTP error path=%s: %s", rel, e)
            errors.append({"path": rel, "error": format_embedding_http_error(e)})
        except httpx.RequestError as e:
            logger.warning("RAG ingest embedding unreachable path=%s: %s", rel, e)
            errors.append({"path": rel, "error": format_embedding_request_error(e)})
        except Exception as e:
            logger.warning("RAG ingest failed path=%s: %s", rel, e)
            errors.append({"path": rel, "error": str(e)})

    orphans_removed = 0
    if incremental and not purge_first and not config_changed:
        for uri, meta in existing.items():
            if uri in seen_uris:
                continue
            doc_id = meta.get("id")
            if doc_id is not None and db.rag_delete_document_by_id(int(doc_id)):
                orphans_removed += 1

    ok = len(errors) == 0
    if ok and (files_ok or files_skipped) and not config_changed:
        operator_settings.set_rag_docs_ingest_fingerprint(compute_rag_ingest_fingerprint())
    elif ok and files_ok and config_changed:
        operator_settings.set_rag_docs_ingest_fingerprint(compute_rag_ingest_fingerprint())

    return {
        "ok": ok,
        "domain": domain,
        "docs_root": str(docs_root),
        "incremental": incremental and not purge_first and not config_changed,
        "ingest_config_changed": config_changed,
        "purge_deleted_documents": deleted_docs,
        "orphans_removed": orphans_removed,
        "files_skipped_unchanged": len(files_skipped),
        "files_ingested": len(files_ok),
        "chunk_count_total": total_chunks,
        "files": files_ok,
        "files_skipped": files_skipped,
        "errors": errors,
    }


def _empty_summary(
    domain: str,
    docs_root: Path,
    *,
    errors: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "ok": False,
        "domain": domain,
        "docs_root": str(docs_root),
        "incremental": False,
        "ingest_config_changed": False,
        "purge_deleted_documents": 0,
        "orphans_removed": 0,
        "files_skipped_unchanged": 0,
        "files_ingested": 0,
        "chunk_count_total": 0,
        "files": [],
        "files_skipped": [],
        "errors": errors,
    }
