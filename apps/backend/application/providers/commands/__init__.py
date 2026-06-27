"""Provider commands."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderEndpointInput:
    provider_id: str
    kind: str
    label: str
    base_url: str
    enabled: bool = True
    api_header_name: str = "Authorization"
    api_key: str | None = None
    model_default: str | None = None
    max_parallel: int = 1
    options: dict[str, Any] | None = None
    db_id: int | None = None


@dataclass(frozen=True, slots=True)
class SyncProviderEndpointsCommand:
    kind: str
    endpoints: list[ProviderEndpointInput]


@dataclass(frozen=True, slots=True)
class ModelCatalogPreferenceInput:
    provider_id: str
    model_id: str
    visible_in_chat: bool = True
    profile_tags: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class SyncModelCatalogPreferencesCommand:
    preferences: list[ModelCatalogPreferenceInput]
