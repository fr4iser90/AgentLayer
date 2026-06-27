"""Batch-ingest Markdown files into RAG (shared by HTTP admin route and startup bootstrap)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Protocol

from apps.backend.domain.rag.ingest_common import ingest_markdown_paths

logger = logging.getLogger(__name__)

_STARTUP_RAG_DOMAIN = "agentlayer_docs"
_MAX_MARKDOWN_BYTES = 2_000_000
# ``apps/backend/domain/rag/...`` -> repository root (contains ``docs/``).
_DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[4] / "docs"


class RagDocsFileIngestDependencies(Protocol):
    def effective_docs_root_str(self) -> str | None: ...

    def rag_enabled(self) -> bool: ...

    def rag_embedding_ready(self) -> bool: ...

    def user_first_admin_id(self) -> uuid.UUID | None: ...

    def user_tenant_id(self, user_id: uuid.UUID) -> int: ...


_deps: RagDocsFileIngestDependencies | None = None


def register_rag_docs_file_ingest_dependencies(deps: RagDocsFileIngestDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> RagDocsFileIngestDependencies:
    if _deps is None:
        raise RuntimeError("RAG docs file ingest dependencies not registered")
    return _deps


def resolve_docs_root() -> Path:
    s = _require_deps().effective_docs_root_str()
    if s:
        return Path(s).expanduser().resolve()
    return _DEFAULT_DOCS_DIR.resolve()


def ingest_markdown_tree(
    tenant_id: int,
    user_id: uuid.UUID,
    docs_root: Path,
    domain: str,
    *,
    purge_first: bool = False,
    incremental: bool = True,
) -> dict[str, object]:
    """
    Walk ``docs_root`` for ``*.md`` and ingest into RAG.

    Default: incremental sync (skip unchanged files by ``content_sha256`` + ``source_uri``).
    ``purge_first=True``: full rebuild for that tenant+domain (admin reindex).
    """
    paths = sorted(docs_root.rglob("*.md"))
    return ingest_markdown_paths(
        tenant_id,
        user_id,
        docs_root,
        domain,
        paths,
        source_uri_for_rel=lambda rel: f"agentlayer-docs:{rel}",
        title_for_rel=lambda rel: f"docs/{rel}",
        purge_first=purge_first,
        incremental=incremental,
        workspace_id=None,
    )


def run_startup_rag_docs_ingest() -> None:
    """
    Incremental ingest of ``docs/**/*.md`` when RAG + embedding are configured.

    Uses oldest admin as row owner (``agentlayer_docs`` is tenant-wide for search).
    """
    logger.info("RAG docs startup ingest starting")
    if not _require_deps().rag_enabled():
        logger.info("RAG docs startup ingest skipped (rag disabled)")
        return
    if not _require_deps().rag_embedding_ready():
        logger.info(
            "RAG docs startup ingest skipped (embedding API or rag_embedding_model not configured)"
        )
        return
    admin_id = _require_deps().user_first_admin_id()
    if admin_id is None:
        logger.warning("RAG docs startup ingest skipped (no admin user yet)")
        return
    root = resolve_docs_root()
    if not root.is_dir():
        logger.warning("RAG docs startup ingest skipped (missing docs dir: %s)", root)
        return
    tenant_id = _require_deps().user_tenant_id(admin_id)
    try:
        summary = ingest_markdown_tree(
            tenant_id,
            admin_id,
            root,
            _STARTUP_RAG_DOMAIN,
            purge_first=False,
            incremental=True,
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
        "RAG docs startup ingest: domain=%s ingested=%s skipped=%s orphans=%s chunks=%s "
        "incremental=%s config_changed=%s",
        summary.get("domain"),
        summary.get("files_ingested"),
        summary.get("files_skipped_unchanged"),
        summary.get("orphans_removed"),
        summary.get("chunk_count_total"),
        summary.get("incremental"),
        summary.get("ingest_config_changed"),
    )
