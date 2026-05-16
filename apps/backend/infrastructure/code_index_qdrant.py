"""Qdrant-based code index service for persistent symbol embeddings."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from apps.backend.core import config
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.embedding_client import embed_one

logger = logging.getLogger(__name__)


def _expected_dim() -> int:
    return int(operator_settings.rag_settings()["embedding_dim"])


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
        self._collection = config.QDRANT_COLLECTION_CODE
        self._dim = _expected_dim()
        self._lock = threading.RLock()
        self._initialized = False

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    def ensure_collection(self) -> bool:
        with self._lock:
            if self._initialized:
                return True
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{self._url}/collections/{self._collection}",
                        headers=self._headers(),
                    )
                    if resp.status_code == 200:
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
                    self._initialized = True
                    return True
            except Exception as e:
                logger.warning("Qdrant init failed: %s", e)
                return False

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
        points: list[dict[str, Any]] = []
        for sym in symbols:
            name = sym.get("name", "")
            if not name:
                continue
            text_for_emb = f"{name} {sym.get('signature', '')} {language}"
            vec = self._embed_text(text_for_emb)
            if vec is None:
                continue
            pid = self._symbol_id(workspace_id, file_path, name, sym.get("line", 0))
            points.append(
                {
                    "id": pid,
                    "vector": vec,
                    "payload": {
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
                    },
                }
            )
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
                logger.warning("Qdrant upsert failed: %s", resp.status_code)
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
                        "query": {"must": must},
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
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self._url}/collections/{self._collection}/points/delete",
                    headers=self._headers(),
                    json={
                        "filter": {"must": [{"key": "workspace_id", "match": {"value": workspace_id}}]}
                    },
                )
            return resp.status_code in (200, 201)
        except Exception:
            return False


_code_index: QdrantCodeIndex | None = None
_index_lock = threading.Lock()


def get_code_index() -> QdrantCodeIndex:
    global _code_index
    with _index_lock:
        if _code_index is None:
            _code_index = QdrantCodeIndex()
        return _code_index