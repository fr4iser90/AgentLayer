"""Unified OpenAI-compatible embedding provider catalog (env + Admin DB)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.embedding_env_providers import (
    EnvEmbeddingProviderRow,
    parse_embedding_env_providers,
)

logger = logging.getLogger(__name__)

_ADMIN_PROVIDER_ID = "embedding_admin"

_SPECS_CACHE: tuple[float, list[EmbeddingProviderSpec]] | None = None
_SPECS_CACHE_TTL_SEC = 2.0


@dataclass(frozen=True)
class EmbeddingProviderSpec:
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    source: str = "env"


def normalize_embedding_provider_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return t or None


def _env_row_spec(row: EnvEmbeddingProviderRow) -> EmbeddingProviderSpec:
    return EmbeddingProviderSpec(
        provider_id=row.provider_id,
        label=row.label,
        base_url=row.base_url,
        api_key=row.api_key,
        api_header_name=row.api_header_name,
        model_default=row.model_default,
        source=row.source,
    )


def _admin_db_spec() -> EmbeddingProviderSpec | None:
    from apps.backend.infrastructure.operator_settings import (
        _cached_row,
        normalize_external_llm_base_url,
    )

    r = _cached_row()
    bu = (str(r.get("embedding_api_base_url") or "").strip() or "")
    if not bu:
        return None
    bu = (normalize_external_llm_base_url(bu) or bu).rstrip("/")
    if not bu:
        return None
    return EmbeddingProviderSpec(
        provider_id=_ADMIN_PROVIDER_ID,
        label="Admin embedding",
        base_url=bu,
        api_key=(str(r.get("embedding_api_key") or "").strip()),
        api_header_name=(str(r.get("embedding_api_header_name") or "").strip() or "X-API-KEY"),
        source="operator_settings",
    )


def list_embedding_provider_specs(*, force_refresh: bool = False) -> list[EmbeddingProviderSpec]:
    global _SPECS_CACHE
    now = time.monotonic()
    if (
        not force_refresh
        and _SPECS_CACHE is not None
        and now - _SPECS_CACHE[0] <= _SPECS_CACHE_TTL_SEC
    ):
        return list(_SPECS_CACHE[1])

    specs: list[EmbeddingProviderSpec] = []
    seen: set[str] = set()
    seen_urls: set[str] = set()

    for row in parse_embedding_env_providers():
        sp = _env_row_spec(row)
        url_key = sp.base_url.rstrip("/").lower()
        if sp.provider_id not in seen and sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(url_key)

    admin = _admin_db_spec()
    if admin and admin.base_url:
        url_key = admin.base_url.rstrip("/").lower()
        if admin.provider_id not in seen and url_key not in seen_urls:
            specs.append(admin)
            seen.add(admin.provider_id)

    _SPECS_CACHE = (now, specs)
    return list(specs)


def get_embedding_provider_spec(provider_id: str) -> EmbeddingProviderSpec | None:
    pid = normalize_embedding_provider_id(provider_id)
    if not pid:
        return None
    for spec in list_embedding_provider_specs():
        if spec.provider_id == pid:
            return spec
    return None


def resolve_active_embedding_provider_id() -> str | None:
    from apps.backend.infrastructure.operator_settings import _cached_row

    db_active = (str(_cached_row().get("rag_embedding_provider_id") or "").strip())
    if db_active and get_embedding_provider_spec(db_active):
        return normalize_embedding_provider_id(db_active)

    specs = list_embedding_provider_specs()
    if specs:
        return specs[0].provider_id
    return None


def resolve_active_embedding_spec() -> EmbeddingProviderSpec | None:
    pid = resolve_active_embedding_provider_id()
    if not pid:
        return None
    return get_embedding_provider_spec(pid)


def invalidate_embedding_provider_specs_cache() -> None:
    global _SPECS_CACHE
    _SPECS_CACHE = None
