"""Qdrant-based code index service for persistent symbol embeddings."""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx

from apps.backend.core import config
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.code_qdrant_collection import (
    QdrantCodeTarget,
    invalidate_code_qdrant_target_cache,
    resolve_code_qdrant_target,
)
from apps.backend.infrastructure.embedding_client import embed_one

logger = logging.getLogger(__name__)


@dataclass
class CodeSymbol:
    id: str
    kind: str
    name: str
    file_path: str
    line: int
    col: int
    end_line: int
    end_col: int
    signature: str
    language: str
    workspace_id: str
    vector: list[float] = field(default_factory=list)


class QdrantCodeIndex:
    def __init__(self) -> None:
        self._url = (config.QDRANT_URL or "").strip().rstrip("/")
        self._api_key = config.QDRANT_API_KEY or ""
        self._collection = ""
        self._dim = 0
        self._target: QdrantCodeTarget | None = None
        self._lock = threading.RLock()
        self._initialized = False
        self._refresh_target()

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    def _refresh_target(self) -> QdrantCodeTarget:
        target = resolve_code_qdrant_target()
        if (
            self._target is None
            or target.collection != self._collection
            or target.embedding_dim != self._dim
        ):
            self._collection = target.collection
            self._dim = target.embedding_dim
            self._target = target
            self._initialized = False
        return target

    def target_info(self) -> dict[str, Any]:
        t = self._refresh_target()
        return {
            "collection": t.collection,
            "embedding_dim": t.embedding_dim,
            "base_collection": t.base_collection,
            "auto_switched": t.auto_switched,
            "note": t.note,
        }

    def ensure_collection(self) -> bool:
        if not self._url:
            return False
        with self._lock:
            target = self._refresh_target()
            if self._initialized and self._collection == target.collection:
                return True
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{self._url}/collections/{self._collection}",
                        headers=self._headers(),
                    )
                    if resp.status_code == 200:
                        existing_dim = None
                        try:
                            from apps.backend.infrastructure.code_qdrant_collection import (
                                _parse_collection_dim,
                            )

                            existing_dim = _parse_collection_dim(resp.json())
                        except Exception:
                            pass
                        if existing_dim is not None and existing_dim != self._dim:
                            logger.error(
                                "Qdrant collection %r has dim=%s but rag_embedding_dim=%s",
                                self._collection,
                                existing_dim,
                                self._dim,
                            )
                            return False
                        self._initialized = True
                        return True
                    if resp.status_code != 404:
                        logger.warning("Qdrant collection check failed: %s", resp.status_code)
                        return False
                    create_resp = client.put(
                        f"{self._url}/collections/{self._collection}",
                        headers=self._headers(),
                        json={
                            "vectors": {
                                "size": self._dim,
                                "distance": "Cosine",
                            },
                        },
                    )
                    if create_resp.status_code not in (200, 201):
                        logger.warning(
                            "Qdrant collection create failed: %s %s",
                            create_resp.status_code,
                            create_resp.text,
                        )
                        return False
                    logger.info(
                        "Created Qdrant collection %r (dim=%s)",
                        self._collection,
                        self._dim,
                    )
                    self._initialized = True
                    return True
            except Exception as e:
                logger.warning("Qdrant init failed: %s", e)
                return False

    def _embedding_model(self) -> str:
        return (operator_settings.rag_settings().get("embedding_model") or "").strip()

    def _embed_text(self, text: str) -> list[float] | None:
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            return embed_one(raw)
        except Exception as e:
            logger.debug("code index embed failed: %s", e)
            return None

    def _symbol_id(self, workspace_id: str, file_path: str, name: str, line: int) -> str:
        raw = f"{workspace_id}:{file_path}:{name}:{line}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def index_symbols(
        self,
        symbols: list[dict[str, Any]],
        file_path: str,
        language: str,
        workspace_id: str,
    ) -> int:
        if not self.ensure_collection():
            return 0
        model = self._embedding_model()
        points: list[dict[str, Any]] = []
        for sym in symbols:
            name = sym.get("name", "")
            if not name:
                continue
            text_for_emb = f"{name} {sym.get('signature', '')} {language}"
            vec = self._embed_text(text_for_emb)
            if vec is None:
                continue
            if len(vec) != self._dim:
                logger.warning(
                    "skip symbol %s:%s — vector dim %s != collection %r dim %s",
                    file_path,
                    name,
                    len(vec),
                    self._collection,
                    self._dim,
                )
                continue
            pid = self._symbol_id(workspace_id, file_path, name, sym.get("line", 0))
            payload: dict[str, Any] = {
                "kind": sym.get("kind", "unknown"),
                "name": name,
                "file_path": file_path,
                "line": sym.get("line", 0),
                "col": sym.get("col", 0),
                "end_line": sym.get("end_line", 0),
                "end_col": sym.get("end_col", 0),
                "signature": sym.get("signature", ""),
                "language": language,
                "workspace_id": workspace_id,
                "embedding_dim": self._dim,
            }
            if model:
                payload["embedding_model"] = model
            points.append({"id": pid, "vector": vec, "payload": payload})
        if not points:
            return 0
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.put(
                    f"{self._url}/collections/{self._collection}/points",
                    headers=self._headers(),
                    json={"points": points},
                )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Qdrant upsert failed: %s %s",
                    resp.status_code,
                    (resp.text or "")[:300],
                )
                return 0
            return len(points)
        except Exception as e:
            logger.warning("Qdrant upsert error: %s", e)
            return 0

    def search(
        self,
        query: str,
        workspace_id: str,
        limit: int = 20,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.ensure_collection():
            return []
        vec = self._embed_text(query)
        if vec is None:
            return []
        must = [{"key": "workspace_id", "match": {"value": workspace_id}}]
        if kind:
            must.append({"key": "kind", "match": {"value": kind}})
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self._url}/collections/{self._collection}/points/search",
                    headers=self._headers(),
                    json={
                        "vector": vec,
                        "limit": limit,
                        "filter": {"must": must},
                    },
                )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results: list[dict[str, Any]] = []
            for r in data.get("result", []):
                p = r.get("payload", {})
                p["score"] = r.get("score", 0)
                results.append(p)
            return results
        except Exception:
            return []

    def delete_workspace(self, workspace_id: str) -> bool:
        if not self.ensure_collection():
            return False
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self._url}/collections/{self._collection}/points/delete",
                    headers=self._headers(),
                    json={
                        "filter": {
                            "must": [{"key": "workspace_id", "match": {"value": workspace_id}}]
                        }
                    },
                )
            return resp.status_code in (200, 201)
        except Exception:
            return False


_code_index: QdrantCodeIndex | None = None
_index_lock = threading.Lock()


def invalidate_code_index_cache() -> None:
    global _code_index
    invalidate_code_qdrant_target_cache()
    with _index_lock:
        _code_index = None


def get_code_index() -> QdrantCodeIndex:
    global _code_index
    with _index_lock:
        if _code_index is None:
            _code_index = QdrantCodeIndex()
        else:
            _code_index._refresh_target()
        return _code_index
