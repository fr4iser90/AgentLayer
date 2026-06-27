"""Single entry point for text embeddings (RAG, memory, Qdrant code index, tool ranking).

Configure via numbered env providers (``EMBEDDING_PROVIDER_1_BASE_URL``, …) and/or Admin → Memory & RAG.
Active provider: ``rag_embedding_provider_id`` in operator settings (Admin UI), else first configured env provider.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_EMBED_HTTP_ERROR_BODY_MAX = 2000

from apps.backend.infrastructure.platform import config as cfgmod
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.providers.embedding_catalog_providers import (
    EmbeddingProviderSpec,
    list_embedding_provider_specs,
    resolve_active_embedding_provider_id,
    resolve_active_embedding_spec,
)
from apps.backend.infrastructure.providers.embedding_chunking import (
    remember_embedding_limits_from_error_body,
    truncate_text_for_embedding,
)
from apps.backend.infrastructure.providers.openai_compat_http import http_post_json

_HDR_NAME_TOKEN = re.compile(r"^[!#$%&'*+.0-9A-Z^_`a-z|~-]{1,128}\Z")


def _strip_env_value(raw: str | None) -> str:
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


def _normalized_base_for_spec(spec: EmbeddingProviderSpec) -> str:
    from apps.backend.infrastructure.settings.operator_settings import normalize_external_llm_base_url

    return (normalize_external_llm_base_url(spec.base_url) or spec.base_url).rstrip("/")


def _normalized_embedding_base() -> str:
    spec = resolve_active_embedding_spec()
    if spec is None:
        return ""
    return _normalized_base_for_spec(spec)


def _embeddings_url(*, spec: EmbeddingProviderSpec | None = None) -> str:
    active = spec or resolve_active_embedding_spec()
    if active is None:
        raise ValueError(
            "No embedding provider configured. Set EMBEDDING_PROVIDER_1_BASE_URL in .env "
            "or configure Admin → Interfaces → Memory & RAG."
        )
    b = _normalized_base_for_spec(active)
    low = b.lower()
    if low.endswith("/embeddings"):
        return b
    return f"{b}/v1/embeddings"


def _embedding_models_list_url(*, spec: EmbeddingProviderSpec | None = None) -> str | None:
    active = spec or resolve_active_embedding_spec()
    if active is None:
        return None
    from apps.backend.infrastructure.settings.operator_settings import external_models_list_url

    return external_models_list_url(_normalized_base_for_spec(active))


def _auth_headers_for_spec(spec: EmbeddingProviderSpec) -> dict[str, str]:
    out: dict[str, str] = {"Content-Type": "application/json"}
    secret = (spec.api_key or "").strip()
    hn = (spec.api_header_name or "X-API-KEY").strip() or "X-API-KEY"
    if not secret:
        return out
    if hn.lower() == "authorization":
        out["Authorization"] = (
            secret if secret.lower().startswith("bearer ") else f"Bearer {secret}"
        )
        return out
    if _HDR_NAME_TOKEN.match(hn):
        out[hn] = secret
        return out
    raise ValueError(
        f"embedding API header name {hn!r} is not a valid HTTP header token "
        "(use e.g. X-API-KEY or Authorization)."
    )


def _embedding_request_headers(*, spec: EmbeddingProviderSpec | None = None) -> dict[str, str]:
    active = spec or resolve_active_embedding_spec()
    if active is None:
        raise ValueError("No active embedding provider configured.")
    return _auth_headers_for_spec(active)


def _embedding_url_and_headers(
    *, spec: EmbeddingProviderSpec | None = None
) -> tuple[str, dict[str, str]]:
    if resolve_active_embedding_spec() is None and spec is None:
        raise ValueError(
            "Embeddings require EMBEDDING_PROVIDER_N_* in .env or embedding settings in Admin → Memory & RAG."
        )
    return _embeddings_url(spec=spec), _embedding_request_headers(spec=spec)


def _ensure_embedding_provider_allowed(spec: EmbeddingProviderSpec) -> None:
    from apps.backend.domain.shared.identity import get_identity
    from apps.backend.infrastructure.providers.model_access_policy import is_provider_capability_allowed

    tenant_id, user_id = get_identity()
    if user_id is None:
        return
    if not is_provider_capability_allowed(
        "embedding",
        spec.provider_id,
        tenant_id=tenant_id,
        user_id=user_id,
    ):
        raise ValueError("embedding provider disabled for this user")


def invalidate_embedding_catalog_cache() -> None:
    global _EMBED_HEALTH_CACHE
    _EMBED_HEALTH_CACHE = None
    from apps.backend.infrastructure.providers.embedding_catalog_providers import (
        invalidate_embedding_provider_specs_cache,
    )

    invalidate_embedding_provider_specs_cache()


def fetch_embedding_models_list(
    *,
    timeout: float = 15.0,
    provider_id: str | None = None,
) -> tuple[list[str], str | None]:
    """``GET …/v1/models`` for the active (or given) embedding provider."""
    from apps.backend.infrastructure.providers.embedding_catalog_providers import get_embedding_provider_spec

    if provider_id:
        spec = get_embedding_provider_spec(provider_id)
    else:
        spec = resolve_active_embedding_spec()
    if spec is None:
        return [], "Embedding-API nicht konfiguriert (EMBEDDING_PROVIDER_1_BASE_URL oder Admin)"
    url = _embedding_models_list_url(spec=spec)
    if not url:
        return [], "Embedding-API nicht konfiguriert"
    try:
        headers = _auth_headers_for_spec(spec)
    except ValueError as e:
        return [], str(e)
    from apps.backend.infrastructure.providers.openai_compat_http import http_get_json

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
    provider_id: str | None = None,
) -> list[float]:
    from apps.backend.infrastructure.providers.embedding_catalog_providers import get_embedding_provider_spec

    if provider_id:
        spec = get_embedding_provider_spec(provider_id)
    else:
        spec = resolve_active_embedding_spec()
    if spec is None:
        raise ValueError("No active embedding provider configured.")
    _ensure_embedding_provider_allowed(spec)
    raw = (text or "").strip()
    if not raw:
        raise ValueError("embedding text is empty")
    rs = operator_settings.rag_settings()
    model = (model_id or rs["embedding_model"] or spec.model_default or "").strip()
    if not model:
        raise ValueError("rag_embedding_model is empty (operator settings — embedding model id)")
    timeout = float(rs["embed_timeout_sec"])
    url, headers = _embedding_url_and_headers(spec=spec)
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
    return len(fetch_embedding_vector_raw("healthcheck", model_id=model_id))


def clear_embedding_health_cache() -> None:
    invalidate_embedding_catalog_cache()


def embedding_http_response_snippet(
    exc: httpx.HTTPStatusError,
    *,
    max_len: int = _EMBED_HTTP_ERROR_BODY_MAX,
) -> str:
    try:
        raw = exc.response.text or ""
    except Exception:
        return ""
    text = raw.strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def format_embedding_http_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    url = str(exc.request.url) if exc.request is not None else "?"
    body = embedding_http_response_snippet(exc)
    msg = f"Embedding API HTTP error: status={status} url={url}"
    if body:
        msg = f"{msg} body={body}"
    return msg


def log_embedding_http_error(exc: httpx.HTTPStatusError, *, context: str = "") -> None:
    prefix = f"{context}: " if context else ""
    body = embedding_http_response_snippet(exc)
    remember_embedding_limits_from_error_body(body)
    logger.warning(
        "%sembedding HTTP status=%s url=%s body=%s",
        prefix,
        exc.response.status_code,
        str(exc.request.url) if exc.request is not None else "?",
        body or "(empty)",
    )


def format_embedding_request_error(exc: httpx.RequestError) -> str:
    return f"Embedding API unreachable: {exc!s}"


def embed_one(text: str) -> list[float]:
    raw = truncate_text_for_embedding((text or "").strip())
    if not raw:
        raise ValueError("embedding text is empty")

    rs = operator_settings.rag_settings()
    model = (rs["embedding_model"] or "").strip()
    if not model:
        raise ValueError("rag_embedding_model is empty (operator settings — embedding model id)")
    timeout = float(rs["embed_timeout_sec"])
    want = _expected_dim()

    spec = resolve_active_embedding_spec()
    if spec is None:
        raise ValueError("No active embedding provider configured.")
    _ensure_embedding_provider_allowed(spec)
    url, headers = _embedding_url_and_headers(spec=spec)
    try:
        data = http_post_json(
            url,
            {"model": model, "input": raw},
            headers=headers,
            timeout=timeout,
        )
    except httpx.HTTPStatusError as e:
        log_embedding_http_error(
            e,
            context=f"embed_one model={model!r} input_chars={len(raw)}",
        )
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
    active_id = resolve_active_embedding_provider_id()
    active = resolve_active_embedding_spec()
    providers_meta: dict[str, Any] = {}
    for spec in list_embedding_provider_specs():
        listed, list_err = fetch_embedding_models_list(timeout=12.0, provider_id=spec.provider_id)
        providers_meta[spec.provider_id] = {
            "label": spec.label,
            "source": spec.source,
            "reachable": bool(listed),
            "detail": list_err,
            "available_models": listed,
        }

    meta: dict[str, Any] = {
        "configured": active is not None,
        "reachable": False,
        "detail": None,
        "model": model or None,
        "embedding_dim": dim,
        "embeddings_url": None,
        "models_url": None,
        "available_models": [],
        "active_provider_id": active_id,
        "providers": providers_meta,
        "note": (
            "Separate from chat. EMBEDDING_PROVIDER_N_* in .env and/or Admin → Memory & RAG; "
            "active provider via Admin → Memory & RAG (or auto: first configured)."
        ),
        "source": active.source if active else None,
    }
    if active is None:
        meta["detail"] = "Embedding-API nicht konfiguriert"
        meta["status_line"] = (
            "Nicht konfiguriert — RAG/Memory-Vektoren inaktiv. Chat und Coding sind davon unabhängig."
        )
        meta["rag_active"] = False
        _EMBED_HEALTH_CACHE = (now, meta)
        return dict(meta)
    try:
        url, headers = _embedding_url_and_headers(spec=active)
    except ValueError as e:
        meta["detail"] = str(e)
        _EMBED_HEALTH_CACHE = (now, meta)
        return dict(meta)
    models_url = _embedding_models_list_url(spec=active)
    if models_url:
        meta["models_url"] = models_url
        listed, list_err = fetch_embedding_models_list(provider_id=active.provider_id)
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
        probe = fetch_embedding_vector_raw("healthcheck", model_id=model, provider_id=active.provider_id)
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
            meta["detail"] = "501 Not Implemented — this host has no /v1/embeddings"
    except httpx.RequestError as e:
        meta["detail"] = str(e)[:200]
    except ValueError as e:
        meta["detail"] = str(e)[:200]
    _EMBED_HEALTH_CACHE = (now, meta)
    return dict(meta)
