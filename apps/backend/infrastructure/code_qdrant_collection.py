"""Pick a Qdrant code-index collection that matches ``rag_embedding_dim``."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.core import config
from apps.backend.infrastructure import operator_settings

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_resolved: QdrantCodeTarget | None = None


@dataclass(frozen=True)
class QdrantCodeTarget:
    collection: str
    embedding_dim: int
    base_collection: str
    auto_switched: bool
    note: str


def _settings_dim() -> int:
    return int(operator_settings.rag_settings()["embedding_dim"])


def _effective_embedding_dim() -> int:
    """
    Prefer live API width over ``rag_embedding_dim`` so routing works even before
    startup sync patches operator_settings (avoids upserts into a 768 collection with 1024 vectors).
    """
    db_dim = _settings_dim()
    try:
        from apps.backend.infrastructure.embedding_client import (
            _normalized_embedding_base,
            probe_embedding_output_dim,
        )

        if not _normalized_embedding_base():
            return db_dim
        probed = probe_embedding_output_dim()
        if probed != db_dim:
            logger.info(
                "code qdrant: embedding API dim=%s, operator_settings rag_embedding_dim=%s → routing by API",
                probed,
                db_dim,
            )
        return probed
    except Exception as e:
        logger.debug("code qdrant: embedding dim probe failed, using operator_settings: %s", e)
        return db_dim


def _qdrant_url() -> str:
    return (config.QDRANT_URL or "").strip().rstrip("/")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    key = config.QDRANT_API_KEY or ""
    if key:
        h["api-key"] = key
    return h


def _parse_collection_dim(payload: dict[str, Any]) -> int | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    params = (result.get("config") or {}).get("params") if isinstance(result.get("config"), dict) else None
    if not isinstance(params, dict):
        return None
    vectors = params.get("vectors")
    if isinstance(vectors, dict):
        if "size" in vectors:
            try:
                return int(vectors["size"])
            except (TypeError, ValueError):
                return None
        for val in vectors.values():
            if isinstance(val, dict) and "size" in val:
                try:
                    return int(val["size"])
                except (TypeError, ValueError):
                    continue
    return None


def fetch_collection_dim(collection: str, *, client: httpx.Client | None = None) -> int | None:
    """Vector width for ``collection``, or None if it does not exist."""
    url = _qdrant_url()
    if not url:
        return None
    try:
        if client is not None:
            resp = client.get(f"{url}/collections/{collection}", headers=_headers())
        else:
            with httpx.Client(timeout=15.0) as c:
                resp = c.get(f"{url}/collections/{collection}", headers=_headers())
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return _parse_collection_dim(resp.json())
    except Exception as e:
        logger.debug("fetch_collection_dim %s: %s", collection, e)
        return None


def resolve_code_qdrant_target(*, force: bool = False) -> QdrantCodeTarget:
    """
    Route code symbols to a collection matching ``rag_embedding_dim``.

  - Base ``code_symbols`` missing → create/use base at current dim.
  - Base exists with same dim → use base.
  - Base exists with different dim → use ``code_symbols_<dim>`` (keeps legacy data).
    """
    global _resolved
    with _lock:
        if _resolved is not None and not force:
            want = _effective_embedding_dim()
            if _resolved.embedding_dim == want:
                return _resolved

        api_dim = _effective_embedding_dim()
        base = (config.QDRANT_COLLECTION_CODE or "code_symbols").strip() or "code_symbols"

        with httpx.Client(timeout=15.0) as client:
            base_dim = fetch_collection_dim(base, client=client)

            if base_dim is None:
                _resolved = QdrantCodeTarget(
                    collection=base,
                    embedding_dim=api_dim,
                    base_collection=base,
                    auto_switched=False,
                    note=f"collection {base!r} will be created with dim={api_dim}",
                )
                return _resolved

            if base_dim == api_dim:
                _resolved = QdrantCodeTarget(
                    collection=base,
                    embedding_dim=api_dim,
                    base_collection=base,
                    auto_switched=False,
                    note=f"using {base!r} (dim={api_dim})",
                )
                return _resolved

            alt = f"{base}_{api_dim}"
            alt_dim = fetch_collection_dim(alt, client=client)
            if alt_dim is not None and alt_dim != api_dim:
                raise ValueError(
                    f"Collection {alt!r} exists but has dim={alt_dim}, expected {api_dim}."
                )

            logger.info(
                "Qdrant code index: %s dim=%s, configured dim=%s → using %r",
                base,
                base_dim,
                api_dim,
                alt,
            )
            _resolved = QdrantCodeTarget(
                collection=alt,
                embedding_dim=api_dim,
                base_collection=base,
                auto_switched=True,
                note=(
                    f"base collection {base!r} is dim={base_dim}, "
                    f"rag_embedding_dim={api_dim}; using {alt!r}"
                ),
            )
            return _resolved


def invalidate_code_qdrant_target_cache() -> None:
    global _resolved
    with _lock:
        _resolved = None
