"""Codebase index API: index and search code symbols via Qdrant."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.core.config import config
from apps.backend.infrastructure.auth import get_current_user, require_admin
from apps.backend.infrastructure.code_index_qdrant import get_code_index
from plugins.tools.capabilities.coding.coding_index_lib import (
    _HAS_TS,
    _SUPPORTED_LANGUAGES,
    CodeIndex,
    get_index,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class IndexCodebaseBody(BaseModel):
    """Body for indexing a codebase."""

    root: str = Field(description="Root directory to index")
    max_files: int = Field(default=5000, ge=100, le=20000)


class SearchSymbolsBody(BaseModel):
    """Body for semantic symbol search."""

    query: str = Field(min_length=1, description="Search query")
    kind: str | None = Field(default=None, description="Filter by symbol kind")
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/v1/codebase/index")
async def index_codebase(request: Request, body: IndexCodebaseBody = Body(...)):
    """
    Index a codebase directory: parse with tree-sitter, store symbols in Qdrant.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")

    if not config.CODING_ENABLED:
        raise HTTPException(status_code=503, detail="coding tools disabled")

    if not _HAS_TS:
        raise HTTPException(status_code=503, detail="tree-sitter not installed")

    root = Path(body.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="root directory not found")

    if config.CODING_ROOT and not str(root).startswith(str(config.CODING_ROOT)):
        if config.CODING_ROOT:
            raise HTTPException(
                status_code=403,
                detail=f"root must be under CODING_ROOT ({config.CODING_ROOT})",
            )

    local_index = get_index()
    max_files = min(body.max_files, 20000)
    stats = local_index.scan(root, max_files=max_files)

    code_index = get_code_index()
    total_indexed = 0
    for file_entry in local_index._files.values():
        if file_entry.symbols:
            count = code_index.index_symbols(
                [s.to_dict() for s in file_entry.symbols],
                file_entry.path,
                file_entry.language,
                str(user.tenant_id),
            )
            total_indexed += count

    return {
        "ok": True,
        "stats": stats,
        "indexed_symbols": total_indexed,
        "files": local_index.file_count,
    }


@router.post("/v1/codebase/search")
async def search_codebase(request: Request, body: SearchSymbolsBody = Body(...)):
    """
    Semantic search of code symbols via Qdrant vector similarity.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")

    code_index = get_code_index()
    results = code_index.search(
        query=body.query,
        workspace_id=str(user.tenant_id),
        limit=body.limit,
        kind=body.kind,
    )

    return {"ok": True, "results": results, "count": len(results)}


@router.delete("/v1/codebase")
async def clear_codebase(request: Request):
    """
    Clear all indexed symbols for the current tenant (workspace).
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")

    code_index = get_code_index()
    ok = code_index.delete_workspace(str(user.tenant_id))

    return {"ok": ok}