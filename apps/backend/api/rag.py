"""RAG: chunking, Ollama embeddings, ingest + search (Postgres pgvector)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

import httpx

from apps.backend.core.config import config
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.openai_compat_http import http_post_json
from apps.backend.infrastructure.db import db
from apps.backend.domain.identity import get_identity

logger = logging.getLogger(__name__)


def _expected_dim() -> int:
    return int(operator_settings.rag_settings()["embedding_dim"])


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    step = chunk_size - overlap
    out: list[str] = []
    i = 0
    while i < len(t):
        out.append(t[i : i + chunk_size])
        i += step
    return [c for c in out if c.strip()]


def _vector_from_ollama_embed_payload(data: dict[str, Any]) -> list[float] | None:
    """Normalize Ollama JSON from ``/api/embed`` or ``/api/embeddings`` into one float vector."""
    emb = data.get("embedding")
    if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
        return [float(x) for x in emb]
    embs = data.get("embeddings")
    if isinstance(embs, list) and embs:
        first = embs[0]
        if isinstance(first, list) and first and isinstance(first[0], (int, float)):
            return [float(x) for x in first]
    return None


def ollama_embed_one(text: str) -> list[float]:
    """
    Single string → one embedding.

    Tries ``POST /api/embed`` (current Ollama), then legacy ``/api/embeddings`` with
    ``prompt``, then ``/api/embeddings`` with ``input`` — different server versions differ.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("embedding text is empty")
    base = (config.OLLAMA_BASE_URL or "").strip().rstrip("/")
    if not base:
        raise ValueError("OLLAMA_BASE_URL is empty")
    rs = operator_settings.rag_settings()
    model = (rs["ollama_model"] or "").strip()
    if not model:
        raise ValueError("rag_ollama_model is empty (operator settings)")
    timeout = float(rs["embed_timeout_sec"])
    want = _expected_dim()

    attempts: list[tuple[str, dict[str, Any]]] = [
        (f"{base}/api/embed", {"model": model, "input": raw}),
        (f"{base}/api/embeddings", {"model": model, "prompt": raw}),
        (f"{base}/api/embeddings", {"model": model, "input": raw}),
    ]
    last: Exception | None = None
    for url, body in attempts:
        try:
            data = http_post_json(url, body, timeout=timeout)
        except httpx.HTTPStatusError as e:
            last = e
            if e.response.status_code == 404:
                continue
            raise
        vec = _vector_from_ollama_embed_payload(data)
        if vec is None:
            last = ValueError("Ollama embed response missing vector")
            continue
        if len(vec) != want:
            raise ValueError(
                f"embedding dim {len(vec)} != configured rag_embedding_dim {want} "
                f"(model {model!r}; align operator_settings with DB vector column)"
            )
        return vec

    hint = (
        f"pull the embedding model on the Ollama host, e.g. `ollama pull {model}` "
        f"(OLLAMA_BASE_URL={base!r})."
    )
    if isinstance(last, httpx.HTTPStatusError):
        raise ValueError(
            f"Ollama returned {last.response.status_code} for all embed endpoints ({hint})"
        ) from last
    if last:
        raise ValueError(f"Ollama embedding failed ({hint})") from last
    raise ValueError(f"Ollama embedding failed ({hint})")


def ingest_for_user(
    tenant_id: int,
    user_id: uuid.UUID,
    domain: str,
    title: str,
    text: str,
    source_uri: str | None = None,
) -> dict[str, Any]:
    rs = operator_settings.rag_settings()
    if not rs["enabled"]:
        raise ValueError("RAG is disabled (operator settings)")
    raw = (text or "").strip()
    if not raw:
        raise ValueError("text is required")
    chunks = chunk_text(raw, rs["chunk_size"], rs["chunk_overlap"])
    if not chunks:
        raise ValueError("no chunks after splitting")
    indexed: list[tuple[int, str, list[float]]] = []
    for i, ch in enumerate(chunks):
        emb = ollama_embed_one(ch)
        indexed.append((i, ch, emb))
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    doc_id, n = db.rag_document_and_chunks_insert(
        tenant_id,
        user_id,
        domain,
        title,
        source_uri,
        sha,
        indexed,
    )
    return {
        "ok": True,
        "document_id": doc_id,
        "chunk_count": n,
        "domain": (domain or "").strip(),
        "title": (title or "").strip(),
    }


def search_for_identity(
    query: str,
    domain: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rs = operator_settings.rag_settings()
    if not rs["enabled"]:
        return []
    q = (query or "").strip()
    if not q:
        return []
    emb = ollama_embed_one(q)
    tenant_id, user_id = get_identity()
    if user_id is None:
        return []
    lim = limit if limit is not None else int(rs["top_k"])
    dom_raw = (domain or "").strip() if domain else ""
    dom_lc = dom_raw.lower()
    tenant_wide = bool(dom_lc and dom_lc in operator_settings.effective_rag_tenant_shared_domains())
    return db.rag_vector_search(
        tenant_id,
        user_id,
        emb,
        domain,
        int(lim),
        tenant_wide_domain=tenant_wide,
    )
