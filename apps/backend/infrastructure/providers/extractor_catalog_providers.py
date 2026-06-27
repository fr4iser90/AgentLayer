"""OpenAI-compatible extractor provider catalog."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.providers.extractor_env_providers import (
    EnvExtractorProviderRow,
    parse_extractor_env_providers,
)

_SPECS_CACHE: tuple[float, list[ExtractorProviderSpec]] | None = None
_SPECS_CACHE_TTL_SEC = 2.0
_LEGACY_DB_PROVIDER_OFFSET = 32


@dataclass(frozen=True)
class ExtractorProviderSpec:
    provider_id: str
    label: str
    base_url: str
    api_key: str
    api_header_name: str
    model_default: str | None = None
    timeout_sec: float = 120.0
    source: str = "env"


def normalize_extractor_provider_id(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    t = "".join(c for c in s if c.isalnum() or c in "_-")[:64]
    return t or None


def db_extractor_provider_id(endpoint_id: int) -> str:
    return f"extractor_provider_db_{int(endpoint_id)}"


def parse_db_extractor_provider_id(provider_id: str) -> int | None:
    pid = (provider_id or "").strip().lower()
    if pid.startswith("extractor_provider_db_"):
        suffix = pid[len("extractor_provider_db_") :]
        return int(suffix) if suffix.isdigit() else None
    if pid.startswith("extractor_provider_"):
        suffix = pid[len("extractor_provider_") :]
        if suffix.isdigit() and int(suffix) > _LEGACY_DB_PROVIDER_OFFSET:
            return int(suffix) - _LEGACY_DB_PROVIDER_OFFSET
    return None


def _env_row_spec(row: EnvExtractorProviderRow) -> ExtractorProviderSpec:
    return ExtractorProviderSpec(
        provider_id=row.provider_id,
        label=row.label,
        base_url=row.base_url,
        api_key=row.api_key,
        api_header_name=row.api_header_name,
        model_default=row.model_default,
        timeout_sec=row.timeout_sec,
        source=row.source,
    )


def _db_endpoint_spec(row: dict[str, Any]) -> ExtractorProviderSpec:
    eid = int(row["id"])
    base = str(row.get("base_url") or "").strip().rstrip("/")
    try:
        options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
        timeout = float(options.get("timeout_sec") or 120.0)
    except (TypeError, ValueError):
        timeout = 120.0
    return ExtractorProviderSpec(
        provider_id=db_extractor_provider_id(eid),
        label=(str(row.get("label") or "").strip() or f"Extractor #{eid}")[:128],
        base_url=base,
        api_key=str(row.get("api_key") or "").strip(),
        api_header_name=str(row.get("api_header_name") or "").strip() or "X-API-KEY",
        model_default=(str(row.get("model_default") or "").strip() or None),
        timeout_sec=max(1.0, min(timeout, 1800.0)),
        source="db",
    )


def _provider_url_key(base_url: str) -> str:
    from apps.backend.infrastructure.settings.operator_settings import normalize_external_llm_base_url

    return (normalize_external_llm_base_url(base_url) or base_url.rstrip("/")).lower()


def list_extractor_provider_specs(*, force_refresh: bool = False) -> list[ExtractorProviderSpec]:
    global _SPECS_CACHE
    now = time.monotonic()
    if (
        not force_refresh
        and _SPECS_CACHE is not None
        and now - _SPECS_CACHE[0] <= _SPECS_CACHE_TTL_SEC
    ):
        return list(_SPECS_CACHE[1])

    specs: list[ExtractorProviderSpec] = []
    seen: set[str] = set()
    seen_urls: set[str] = set()
    try:
        db_rows = db.operator_provider_endpoints_list_all("extractor")
    except RuntimeError:
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
    for row in parse_extractor_env_providers():
        sp = _env_row_spec(row)
        url_key = _provider_url_key(sp.base_url)
        if sp.provider_id not in seen and sp.base_url and url_key not in seen_urls:
            specs.append(sp)
            seen.add(sp.provider_id)
            seen_urls.add(url_key)
    _SPECS_CACHE = (now, specs)
    return list(specs)


def resolve_active_extractor_provider_id() -> str | None:
    from apps.backend.infrastructure.settings.operator_settings import _cached_row

    configured = normalize_extractor_provider_id(_cached_row().get("extractor_provider_id"))
    if configured and get_extractor_provider_spec(configured):
        return configured
    specs = list_extractor_provider_specs()
    return specs[0].provider_id if specs else None


def get_extractor_provider_spec(provider_id: str | None) -> ExtractorProviderSpec | None:
    pid = normalize_extractor_provider_id(provider_id) or resolve_active_extractor_provider_id()
    specs = list_extractor_provider_specs()
    if pid:
        for spec in specs:
            if spec.provider_id == pid:
                return spec
        legacy_db_id = parse_db_extractor_provider_id(pid)
        if legacy_db_id is not None:
            db_pid = db_extractor_provider_id(legacy_db_id)
            for spec in specs:
                if spec.provider_id == db_pid:
                    return spec
        for row in parse_extractor_env_providers():
            if normalize_extractor_provider_id(row.provider_id) != pid:
                continue
            env_url_key = _provider_url_key(row.base_url)
            for spec in specs:
                if _provider_url_key(spec.base_url) == env_url_key:
                    return spec
        return None
    return specs[0] if specs else None


def extractor_providers_public_fields() -> dict[str, Any]:
    specs = list_extractor_provider_specs()
    active_id = resolve_active_extractor_provider_id()
    r = None
    try:
        from apps.backend.infrastructure.settings.operator_settings import _cached_row

        r = _cached_row()
    except Exception:
        r = {}
    return {
        "extractor_api_base_url": str((r or {}).get("extractor_api_base_url") or "").strip() or None,
        "extractor_api_base_effective": (
            get_extractor_provider_spec(active_id).base_url if active_id and get_extractor_provider_spec(active_id) else None
        ),
        "extractor_api_key_configured": bool(
            (get_extractor_provider_spec(active_id).api_key if active_id and get_extractor_provider_spec(active_id) else "")
            or str((r or {}).get("extractor_api_key") or "").strip()
        ),
        "extractor_api_header_name": str((r or {}).get("extractor_api_header_name") or "").strip() or None,
        "extractor_api_header_name_effective": (
            get_extractor_provider_spec(active_id).api_header_name if active_id and get_extractor_provider_spec(active_id) else "X-API-KEY"
        ),
        "extractor_provider_id": str((r or {}).get("extractor_provider_id") or "").strip() or None,
        "extractor_provider_id_effective": active_id,
        "extractor_model": str((r or {}).get("extractor_model") or "").strip(),
        "extractor_timeout_sec": float((r or {}).get("extractor_timeout_sec") or 120.0),
        "extractor_providers": [
            {
                "provider_id": s.provider_id,
                "label": s.label,
                "source": s.source,
                "base_url": s.base_url,
                "model_default": s.model_default,
                "timeout_sec": s.timeout_sec,
            }
            for s in specs
        ],
        "extractor_provider_configured": bool(specs),
    }


def invalidate_extractor_provider_specs_cache() -> None:
    global _SPECS_CACHE
    _SPECS_CACHE = None

