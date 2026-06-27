"""Postgres adapters for provider repository ports."""
from __future__ import annotations

from typing import Any

from apps.backend.domain.providers.entities import ModelCatalogPreference, ProviderEndpoint
from apps.backend.domain.providers.repositories import (
    ModelCatalogPreferenceRepository,
    ProviderEndpointRepository,
)
from apps.backend.domain.providers.value_objects import ProviderId, ProviderKind, ProviderLabel, normalize_provider_kind
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.providers.model_catalog_providers import db_catalog_provider_id, parse_db_catalog_provider_id


class PostgresProviderEndpointRepository(ProviderEndpointRepository):
    def list(self, *, kind: ProviderKind | None = None) -> list[ProviderEndpoint]:
        if kind == "llm":
            rows = db.external_llm_endpoints_list_all()
            return [_llm_endpoint_from_row(row) for row in rows]
        if kind is not None:
            rows = db.operator_provider_endpoints_list_all(_db_kind(kind))
            return [_operator_endpoint_from_row(row) for row in rows]
        endpoints = [_llm_endpoint_from_row(row) for row in db.external_llm_endpoints_list_all()]
        for db_kind in ("embedding", "voice", "extractor", "chat"):
            mapped_kind = "llm" if db_kind == "chat" else db_kind
            endpoints.extend(
                _operator_endpoint_from_row(row, forced_kind=mapped_kind)
                for row in db.operator_provider_endpoints_list_all(db_kind)
            )
        return endpoints

    def get(self, provider_id: ProviderId) -> ProviderEndpoint | None:
        raw = str(provider_id)
        llm_id = parse_db_catalog_provider_id(raw)
        if llm_id is not None:
            row = db.external_llm_endpoint_by_id(llm_id)
            return _llm_endpoint_from_row(row) if row else None
        parts = raw.rsplit("_db_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            kind = normalize_provider_kind(parts[0])
            row = db.operator_provider_endpoint_by_id(_db_kind(kind), int(parts[1]))
            return _operator_endpoint_from_row(row, forced_kind=kind) if row else None
        return None

    def sync(self, *, kind: ProviderKind, endpoints: list[ProviderEndpoint]) -> None:
        if kind == "llm":
            db.external_llm_endpoints_sync([_llm_row(endpoint, idx) for idx, endpoint in enumerate(endpoints)])
            return
        db.operator_provider_endpoints_sync(
            _db_kind(kind),
            [_operator_row(endpoint, idx) for idx, endpoint in enumerate(endpoints)],
        )


class PostgresModelCatalogPreferenceRepository(ModelCatalogPreferenceRepository):
    def list(self) -> list[ModelCatalogPreference]:
        return [_pref_from_row(row) for row in db.model_catalog_prefs_list_all()]

    def sync(self, preferences: list[ModelCatalogPreference]) -> None:
        db.model_catalog_prefs_sync(
            [
                {
                    "provider_id": str(pref.provider_id),
                    "model_id": pref.model_id,
                    "visible_in_chat": pref.visible_in_chat,
                    "profile_tags": list(pref.profile_tags),
                    "sort_order": pref.sort_order,
                }
                for pref in preferences
            ]
        )


def _db_kind(kind: ProviderKind) -> str:
    return "chat" if kind == "llm" else kind


def _llm_endpoint_from_row(row: dict[str, Any]) -> ProviderEndpoint:
    endpoint_id = int(row.get("id") or 0)
    return ProviderEndpoint(
        provider_id=ProviderId.parse(db_catalog_provider_id(endpoint_id)),
        kind="llm",
        label=ProviderLabel.parse(str(row.get("label") or f"Provider {endpoint_id}")),
        base_url=str(row.get("base_url") or ""),
        enabled=bool(row.get("enabled")),
        api_header_name=str(row.get("api_header_name") or "Authorization"),
        api_key=str(row.get("api_key") or "") or None,
        model_default=str(row.get("model_default") or "") or None,
        max_parallel=int(row.get("max_parallel") or 1),
        db_id=endpoint_id,
    )


def _operator_endpoint_from_row(
    row: dict[str, Any],
    *,
    forced_kind: ProviderKind | None = None,
) -> ProviderEndpoint:
    endpoint_id = int(row.get("id") or 0)
    kind = forced_kind or normalize_provider_kind(str(row.get("kind") or "embedding"))
    return ProviderEndpoint(
        provider_id=ProviderId.parse(f"{kind}_db_{endpoint_id}"),
        kind=kind,
        label=ProviderLabel.parse(str(row.get("label") or f"{kind} provider {endpoint_id}")),
        base_url=str(row.get("base_url") or ""),
        enabled=bool(row.get("enabled")),
        api_header_name=str(row.get("api_header_name") or "Authorization"),
        api_key=str(row.get("api_key") or "") or None,
        model_default=str(row.get("model_default") or "") or None,
        max_parallel=int(row.get("max_parallel") or 1),
        options=row.get("options_json") if isinstance(row.get("options_json"), dict) else {},
        db_id=endpoint_id,
    )


def _llm_row(endpoint: ProviderEndpoint, sort_order: int) -> dict[str, Any]:
    return {
        "id": endpoint.db_id,
        "sort_order": sort_order,
        "enabled": endpoint.enabled,
        "label": str(endpoint.label),
        "base_url": endpoint.base_url,
        "api_key": endpoint.api_key,
        "api_header_name": endpoint.api_header_name,
        "model_default": endpoint.model_default,
        "max_parallel": endpoint.max_parallel,
    }


def _operator_row(endpoint: ProviderEndpoint, sort_order: int) -> dict[str, Any]:
    return {
        "id": endpoint.db_id,
        "sort_order": sort_order,
        "enabled": endpoint.enabled,
        "label": str(endpoint.label),
        "base_url": endpoint.base_url,
        "api_key": endpoint.api_key,
        "api_header_name": endpoint.api_header_name,
        "model_default": endpoint.model_default,
        "max_parallel": endpoint.max_parallel,
        "options_json": endpoint.options,
    }


def _pref_from_row(row: dict[str, Any]) -> ModelCatalogPreference:
    tags = row.get("profile_tags")
    return ModelCatalogPreference(
        provider_id=ProviderId.parse(str(row.get("provider_id") or "")),
        model_id=str(row.get("model_id") or ""),
        visible_in_chat=bool(row.get("visible_in_chat", True)),
        profile_tags=tuple(tags if isinstance(tags, list) else []),
        sort_order=int(row.get("sort_order") or 0),
    )
