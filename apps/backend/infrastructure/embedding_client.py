"""Single entry point for text embeddings (RAG, memory, Qdrant code index, tool ranking).

Uses **only** explicit env (no Ollama, llama.cpp, or chat URL reuse):

- ``EMBEDDING_BASE_URL`` — OpenAI-compatible API base (e.g. ``https://host/v1``)
- ``EMBEDDING_API_HEADER_NAME`` — HTTP header name for the secret (e.g. ``X-API-KEY``)
- ``EMBEDDING_API_HEADER_VALUE`` — secret sent in that header

Model id and dimension: ``operator_settings`` ``rag_embedding_model`` / ``rag_embedding_dim``.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from apps.backend.core import config as cfgmod
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.openai_compat_http import http_post_json

_HDR_NAME_TOKEN = re.compile(r"^[!#$%&'*+.0-9A-Z^_`a-z|~-]{1,128}\Z")


def _strip_env_value(raw: str | None) -> str:
    """Trim env value; strip one pair of surrounding quotes from .env mistakes."""
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


def _expected_dim() -> int:
    return int(operator_settings.rag_settings()["embedding_dim"])


def _vector_from_openai_embeddings_payload(data: dict[str, Any]) -> list[float] | None:
    arr = data.get("data")
    if not isinstance(arr, list) or not arr:
        return None
    first = arr[0]
    if not isinstance(first, dict):
        return None
    emb = first.get("embedding")
    if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
        return [float(x) for x in emb]
    return None


def _normalized_embedding_base() -> str:
    base = _strip_env_value(getattr(cfgmod, "EMBEDDING_BASE_URL", None))
    if base:
        from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

        return (normalize_external_llm_base_url(base) or base).rstrip("/")
    from apps.backend.infrastructure.operator_settings import resolved_embedding_api_base_url

    return resolved_embedding_api_base_url()


def _embeddings_url(api_base: str | None = None) -> str:
    b = (api_base or _normalized_embedding_base()).strip().rstrip("/")
    if not b:
        raise ValueError("EMBEDDING_BASE_URL is empty")
    low = b.lower()
    if low.endswith("/embeddings"):
        return b
    return f"{b}/v1/embeddings"


def _embedding_models_list_url() -> str | None:
    b = _normalized_embedding_base()
    if not b:
        return None
    from apps.backend.infrastructure.operator_settings import external_models_list_url

    return external_models_list_url(b)


def _auth_headers_for_secret(header_name: str, secret: str) -> dict[str, str]:
    out: dict[str, str] = {"Content-Type": "application/json"}
    if not secret:
        return out
    hn = (header_name or "X-API-KEY").strip() or "X-API-KEY"
    if hn.lower() == "authorization":
        out["Authorization"] = f"Bearer {secret}" if not secret.lower().startswith("bearer ") else secret
        return out
    if _HDR_NAME_TOKEN.match(hn):
        out[hn] = secret
        return out
    raise ValueError(
        f"EMBEDDING_API_HEADER_NAME {hn!r} is not a valid HTTP header token "
        "(use e.g. X-API-KEY or Authorization)."
    )


def _embedding_request_headers() -> dict[str, str]:
    """Env ``EMBEDDING_API_HEADER_VALUE`` overrides DB ``embedding_api_key``."""
    from apps.backend.infrastructure.operator_settings import (
        resolved_embedding_api_header_name,
        resolved_embedding_api_key,
    )

    return _auth_headers_for_secret(
        resolved_embedding_api_header_name(),
        resolved_embedding_api_key(),
    )


def _embedding_url_and_headers() -> tuple[str, dict[str, str]]:
    if not _normalized_embedding_base():
        raise ValueError(
            "Embeddings require EMBEDDING_BASE_URL in .env or embedding_api_base_url in operator "
            "settings (OpenAI-compatible host, e.g. https://host or https://host/v1). "
            "OLLAMA_BASE_URL is not used for embeddings unless enabled via setup."
        )
    return _embeddings_url(), _embedding_request_headers()


def invalidate_embedding_catalog_cache() -> None:
    global _EMBED_HEALTH_CACHE
    _EMBED_HEALTH_CACHE = None


def fetch_embedding_models_list(*, timeout: float = 15.0) -> tuple[list[str], str | None]:
    """``GET …/v1/models`` at ``EMBEDDING_BASE_URL`` → model ids for the UI dropdown."""
    url = _embedding_models_list_url()
    if not url:
        return [], "Embedding-API nicht konfiguriert (EMBEDDING_BASE_URL oder Setup)"
    try:
        headers = _embedding_request_headers()
    except ValueError as e:
        return [], str(e)
    from apps.backend.infrastructure.openai_compat_http import http_get_json

    status, text, data = http_get_json(url, headers=headers, timeout=timeout)
    if status != 200 or not isinstance(data, dict):
        detail = (text or "").strip() or f"http_{status}"
        return [], detail
    ids: list[str] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if isinstance(mid, str) and mid.strip():
            ids.append(mid.strip())
    return ids, None


def fetch_embedding_vector_raw(
    text: str = "healthcheck",
    *,
    model_id: str | None = None,
) -> list[float]:
    """Call the embedding API and return the vector without ``rag_embedding_dim`` validation."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("embedding text is empty")
    rs = operator_settings.rag_settings()
    model = (model_id or rs["embedding_model"] or "").strip()
    if not model:
        raise ValueError("rag_embedding_model is empty (operator settings — embedding model id)")
    timeout = float(rs["embed_timeout_sec"])
    url, headers = _embedding_url_and_headers()
    data = http_post_json(
        url,
        {"model": model, "input": raw},
        headers=headers,
        timeout=timeout,
    )
    vec = _vector_from_openai_embeddings_payload(data)
    if vec is None:
        raise ValueError("embedding response missing data[0].embedding")
    return vec


def probe_embedding_output_dim(*, model_id: str | None = None) -> int:
    """Return embedding width from a live API probe (for syncing ``rag_embedding_dim``)."""
    return len(fetch_embedding_vector_raw("healthcheck", model_id=model_id))


def clear_embedding_health_cache() -> None:
    global _EMBED_HEALTH_CACHE
    _EMBED_HEALTH_CACHE = None


def format_embedding_http_error(exc: httpx.HTTPStatusError) -> str:
    """User-facing message for embedding ingest/search HTTP failures (any provider)."""
    return f"Embedding API HTTP error: {exc!s}"


def format_embedding_request_error(exc: httpx.RequestError) -> str:
    """User-facing message when the configured embedding host is unreachable."""
    return f"Embedding API unreachable: {exc!s}"


def embed_one(text: str) -> list[float]:
    """
    Embed one string via ``POST …/v1/embeddings`` at ``EMBEDDING_BASE_URL`` only.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("embedding text is empty")

    rs = operator_settings.rag_settings()
    model = (rs["embedding_model"] or "").strip()
    if not model:
        raise ValueError("rag_embedding_model is empty (operator settings — embedding model id)")
    timeout = float(rs["embed_timeout_sec"])
    want = _expected_dim()

    url, headers = _embedding_url_and_headers()
    try:
        data = http_post_json(
            url,
            {"model": model, "input": raw},
            headers=headers,
            timeout=timeout,
        )
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as e:
        raise ValueError(f"embeddings request failed ({url}): {e!s}") from e

    vec = _vector_from_openai_embeddings_payload(data)
    if vec is None:
        raise ValueError("embedding response missing data[0].embedding")
    if len(vec) != want:
        raise ValueError(
            f"embedding dim {len(vec)} != configured rag_embedding_dim {want} "
            f"(model {model!r}; align operator_settings with the embedding model output)"
        )
    return vec


_EMBED_HEALTH_CACHE: tuple[float, dict[str, Any]] | None = None
_EMBED_HEALTH_TTL_SEC = 45.0


def embedding_catalog_health(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Probe ``EMBEDDING_*`` for GET ``/v1/models`` ``agentlayer.embedding`` (RAG only; not chat).

    Never uses Ollama / llama.cpp chat URLs.
    """
    import time

    global _EMBED_HEALTH_CACHE
    now = time.monotonic()
    if (
        not force_refresh
        and _EMBED_HEALTH_CACHE is not None
        and now - _EMBED_HEALTH_CACHE[0] <= _EMBED_HEALTH_TTL_SEC
    ):
        return dict(_EMBED_HEALTH_CACHE[1])

    rs = operator_settings.rag_settings()
    model = (rs.get("embedding_model") or "").strip()
    dim = int(rs.get("embedding_dim") or 0)
    base = _normalized_embedding_base()
    meta: dict[str, Any] = {
        "configured": bool(base),
        "reachable": False,
        "detail": None,
        "model": model or None,
        "embedding_dim": dim,
        "embeddings_url": None,
        "models_url": None,
        "available_models": [],
        "note": (
            "Separate from chat. EMBEDDING_BASE_URL in .env and/or embedding_api_base_url from setup; "
            "model id from operator_settings rag_embedding_model."
        ),
        "source": (
            "env"
            if _strip_env_value(getattr(cfgmod, "EMBEDDING_BASE_URL", None))
            else ("operator_settings" if base else None)
        ),
    }
    if not base:
        meta["detail"] = "Embedding-API nicht konfiguriert"
        meta["status_line"] = (
            "Nicht konfiguriert — RAG/Memory-Vektoren inaktiv. Chat und Coding sind davon unabhängig."
        )
        meta["rag_active"] = False
        _EMBED_HEALTH_CACHE = (now, meta)
        return dict(meta)
    try:
        url, headers = _embedding_url_and_headers()
    except ValueError as e:
        meta["detail"] = str(e)
        _EMBED_HEALTH_CACHE = (now, meta)
        return dict(meta)
    models_url = _embedding_models_list_url()
    if models_url:
        meta["models_url"] = models_url
        listed, list_err = fetch_embedding_models_list(timeout=min(12.0, float(rs.get("embed_timeout_sec") or 12.0)))
        meta["available_models"] = listed
        if list_err and not listed:
            meta["models_list_detail"] = list_err
        elif model and model not in listed:
            meta["available_models"] = [model, *listed]
    if not model:
        meta["detail"] = "rag_embedding_model empty (operator settings)"
        meta["embeddings_url"] = url
        _EMBED_HEALTH_CACHE = (now, meta)
        return dict(meta)
    meta["embeddings_url"] = url
    try:
        probe = fetch_embedding_vector_raw("healthcheck", model_id=model)
        meta["reachable"] = True
        meta["rag_active"] = bool(rs.get("enabled", True))
        actual = len(probe)
        meta["actual_embedding_dim"] = actual
        meta["dim_matches_config"] = actual == dim
        if dim and actual != dim:
            meta["dim_mismatch"] = True
            meta["detail"] = (
                f"embedding dim {actual} from API != configured rag_embedding_dim {dim} "
                f"(set rag_embedding_dim to {actual} in Admin → Interfaces)"
            )
    except httpx.HTTPStatusError as e:
        meta["detail"] = (e.response.text or "")[:200].strip() or f"http_{e.response.status_code}"
        if e.response.status_code == 501:
            meta["detail"] = "501 Not Implemented — this host has no /v1/embeddings (use a dedicated embedding API)"
    except httpx.RequestError as e:
        meta["detail"] = str(e)[:200]
    except ValueError as e:
        meta["detail"] = str(e)[:200]
    _EMBED_HEALTH_CACHE = (now, meta)
    return dict(meta)
