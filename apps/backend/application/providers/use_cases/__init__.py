"""Provider use cases."""
from __future__ import annotations

from apps.backend.application.providers.commands import (
    ModelCatalogPreferenceInput,
    ProviderEndpointInput,
    SyncModelCatalogPreferencesCommand,
    SyncProviderEndpointsCommand,
)
from apps.backend.application.providers.dtos import ModelCatalogPreferenceDto, ProviderEndpointDto
from apps.backend.application.providers.queries import ListProviderEndpointsQuery
from apps.backend.domain.providers.entities import ModelCatalogPreference, ProviderEndpoint
from apps.backend.domain.providers.repositories import (
    ModelCatalogPreferenceRepository,
    ProviderEndpointRepository,
)
from apps.backend.domain.providers.value_objects import ProviderId, ProviderLabel, normalize_provider_kind


def _endpoint_to_dto(endpoint: ProviderEndpoint) -> ProviderEndpointDto:
    return ProviderEndpointDto(
        provider_id=str(endpoint.provider_id),
        kind=endpoint.kind,
        label=str(endpoint.label),
        base_url=endpoint.base_url,
        enabled=endpoint.enabled,
        api_header_name=endpoint.api_header_name,
        model_default=endpoint.model_default,
        max_parallel=endpoint.max_parallel,
        options=endpoint.options,
        db_id=endpoint.db_id,
    )


def _pref_to_dto(pref: ModelCatalogPreference) -> ModelCatalogPreferenceDto:
    return ModelCatalogPreferenceDto(
        provider_id=str(pref.provider_id),
        model_id=pref.model_id,
        visible_in_chat=pref.visible_in_chat,
        profile_tags=pref.profile_tags,
        sort_order=pref.sort_order,
    )


def list_provider_endpoints(
    repo: ProviderEndpointRepository,
    query: ListProviderEndpointsQuery,
) -> list[ProviderEndpointDto]:
    kind = normalize_provider_kind(query.kind) if query.kind is not None else None
    return [_endpoint_to_dto(endpoint) for endpoint in repo.list(kind=kind)]


def sync_provider_endpoints(
    repo: ProviderEndpointRepository,
    command: SyncProviderEndpointsCommand,
) -> None:
    kind = normalize_provider_kind(command.kind)
    repo.sync(kind=kind, endpoints=[_endpoint_from_input(item) for item in command.endpoints])


def list_model_catalog_preferences(
    repo: ModelCatalogPreferenceRepository,
) -> list[ModelCatalogPreferenceDto]:
    return [_pref_to_dto(pref) for pref in repo.list()]


def sync_model_catalog_preferences(
    repo: ModelCatalogPreferenceRepository,
    command: SyncModelCatalogPreferencesCommand,
) -> None:
    repo.sync([_pref_from_input(item) for item in command.preferences])


def _endpoint_from_input(item: ProviderEndpointInput) -> ProviderEndpoint:
    return ProviderEndpoint(
        provider_id=ProviderId.parse(item.provider_id),
        kind=normalize_provider_kind(item.kind),
        label=ProviderLabel.parse(item.label),
        base_url=item.base_url,
        enabled=item.enabled,
        api_header_name=item.api_header_name,
        api_key=item.api_key,
        model_default=item.model_default,
        max_parallel=item.max_parallel,
        options=item.options or {},
        db_id=item.db_id,
    )


def _pref_from_input(item: ModelCatalogPreferenceInput) -> ModelCatalogPreference:
    return ModelCatalogPreference(
        provider_id=ProviderId.parse(item.provider_id),
        model_id=item.model_id,
        visible_in_chat=item.visible_in_chat,
        profile_tags=item.profile_tags,
        sort_order=item.sort_order,
    )
