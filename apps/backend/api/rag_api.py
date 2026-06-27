"""Admin HTTP for RAG ingest (admin Bearer only)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.infrastructure.rag_docs_file_ingest_service import ingest_markdown_tree, resolve_docs_root
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.public_error import http_500_detail
from apps.backend.infrastructure.auth import require_admin
from apps.backend.infrastructure.db import db
import apps.backend.api.rag as rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


class IngestDocsBody(BaseModel):
    """Optional body for ``POST /v1/admin/rag/ingest-docs``."""

    docs_root: str | None = Field(
        default=None,
        description="Directory containing Markdown files (default: <repo>/docs).",
    )
    domain: str = Field(default="agentlayer_docs", min_length=1)
    purge_first: bool = Field(
        default=False,
        description="If true, delete all RAG rows for this tenant+domain then re-ingest everything.",
    )
    incremental: bool = Field(
        default=True,
        description="Skip files whose content hash matches DB; remove DB rows for deleted files.",
    )


@router.post("/v1/admin/rag/ingest")
async def admin_rag_ingest(request: Request):
    """
    Ingest plain text into pgvector-backed RAG for the admin's tenant (``users.tenant_id``).
    """
    user = await require_admin(request)
    if not operator_settings.rag_settings()["enabled"]:
        raise HTTPException(status_code=503, detail="RAG disabled (operator settings)")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object expected")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text (non-empty string) is required")
    domain = body.get("domain") if isinstance(body.get("domain"), str) else ""
    title = body.get("title") if isinstance(body.get("title"), str) else ""
    source_uri = body.get("source_uri")
    su = source_uri if isinstance(source_uri, str) and source_uri.strip() else None

    tenant_id = db.user_tenant_id(user.id)
    try:
        out = rag_service.ingest_for_user(
            tenant_id, user.id, domain, title, text, su
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        logger.exception("RAG ingest embedding HTTP error")
        detail = (
            f"Embedding HTTP error: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding HTTP error"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except httpx.RequestError as e:
        logger.exception("RAG ingest cannot reach embedding backend")
        detail = (
            f"Embedding backend unreachable: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding backend unreachable"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except Exception as e:
        logger.exception("RAG ingest failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    return out


@router.post("/v1/admin/rag/ingest-docs")
async def admin_rag_ingest_docs(
    request: Request, body: IngestDocsBody = Body(default_factory=IngestDocsBody)
):
    """
    Walk ``docs_root`` for ``*.md``, ingest each file under ``domain`` (default ``agentlayer_docs``).
    Default: incremental sync (hash + source_uri). Set ``purge_first`` for a full rebuild.
    """
    user = await require_admin(request)
    if not operator_settings.rag_settings()["enabled"]:
        raise HTTPException(status_code=503, detail="RAG disabled (operator settings)")
    opts = body or IngestDocsBody()
    domain = opts.domain.strip()
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required")

    if opts.docs_root:
        root = Path(opts.docs_root).expanduser().resolve()
    else:
        root = resolve_docs_root()

    if not root.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"docs_root not found or not a directory: {root}",
        )

    tenant_id = db.user_tenant_id(user.id)
    try:
        return ingest_markdown_tree(
            tenant_id,
            user.id,
            root,
            domain,
            purge_first=opts.purge_first,
            incremental=opts.incremental and not opts.purge_first,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
