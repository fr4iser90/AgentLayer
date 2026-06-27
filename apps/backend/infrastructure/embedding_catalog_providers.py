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
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)
_LEGACY_DB_PROVIDER_OFFSET = 32

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


def db_embedding_provider_id(endpoint_id: int) -> str:
    return f"embedding_provider_db_{int(endpoint_id)}"


def parse_db_embedding_provider_id(provider_id: str) -> int | None:
    pid = (provider_id or "").strip().lower()
    if pid.startswith("embedding_provider_db_"):
        suffix = pid[len("embedding_provider_db_") :]
        return int(suffix) if suffix.isdigit() else None
    if pid.startswith("embedding_provider_"):
        suffix = pid[len("embedding_provider_") :]
        if suffix.isdigit() and int(suffix) > _LEGACY_DB_PROVIDER_OFFSET:
            return int(suffix) - _LEGACY_DB_PROVIDER_OFFSET
    return None


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


def _db_endpoint_spec(row: dict[str, Any]) -> EmbeddingProviderSpec:
    eid = int(row["id"])
    bu = str(row.get("base_url") or "").strip().rstrip("/")
    return EmbeddingProviderSpec(
        provider_id=db_embedding_provider_id(eid),
        label=(str(row.get("label") or "").strip() or f"Embedding #{eid}")[:128],
        base_url=bu,
        api_key=str(row.get("api_key") or "").strip(),
        api_header_name=str(row.get("api_header_name") or "").strip() or "X-API-KEY",
        model_default=(str(row.get("model_default") or "").strip() or None),
        source="db",
    )


def _provider_url_key(base_url: str) -> str:
    from apps.backend.infrastructure.operator_settings import normalize_external_llm_base_url

    return (normalize_external_llm_base_url(base_url) or base_url.rstrip("/")).lower()


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

    try:
        db_rows = db.operator_provider_endpoints_list_all("embedding")
    except RuntimeError:
        logger.debug("list_embedding_provider_specs: DB pool not ready — env providers only")
        db_rows = []
    for row in db_rows:
        if not row.get("enabled", True):
            continue
        sp = _db_endpoint_spec(row)
        url_key = _provider_url_key(sp.base_url)
        if sp.provider_id not in seen and sp.base_url:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(url_key)

    for row in parse_embedding_env_providers():
        sp = _env_row_spec(row)
        url_key = _provider_url_key(sp.base_url)
        if sp.provider_id not in seen and sp.base_url and url_key not in seen_urls:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(url_key)

    _SPECS_CACHE = (now, specs)
    return list(specs)


def get_embedding_provider_spec(provider_id: str) -> EmbeddingProviderSpec | None:
    pid = normalize_embedding_provider_id(provider_id)
    if not pid:
        return None
    specs = list_embedding_provider_specs()
    for spec in specs:
        if spec.provider_id == pid:
            return spec
    legacy_db_id = parse_db_embedding_provider_id(pid)
    if legacy_db_id is not None:
        db_pid = db_embedding_provider_id(legacy_db_id)
        for spec in specs:
            if spec.provider_id == db_pid:
                return spec
    for row in parse_embedding_env_providers():
        if normalize_embedding_provider_id(row.provider_id) != pid:
            continue
        env_url_key = _provider_url_key(row.base_url)
        for spec in specs:
            if _provider_url_key(spec.base_url) == env_url_key:
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
