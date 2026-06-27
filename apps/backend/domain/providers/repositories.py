"""Repository ports for providers."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.providers.entities import ModelCatalogPreference, ProviderEndpoint
from apps.backend.domain.providers.value_objects import ProviderId, ProviderKind


class ProviderEndpointRepository(Protocol):
    def list(self, *, kind: ProviderKind | None = None) -> list[ProviderEndpoint]: ...

    def get(self, provider_id: ProviderId) -> ProviderEndpoint | None: ...

    def sync(self, *, kind: ProviderKind, endpoints: list[ProviderEndpoint]) -> None: ...


class ModelCatalogPreferenceRepository(Protocol):
    def list(self) -> list[ModelCatalogPreference]: ...

    def sync(self, preferences: list[ModelCatalogPreference]) -> None: ...
