"""Provider DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderEndpointDto:
    provider_id: str
    kind: str
    label: str
    base_url: str
    enabled: bool
    api_header_name: str
    model_default: str | None
    max_parallel: int
    options: dict[str, Any]
    db_id: int | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogPreferenceDto:
    provider_id: str
    model_id: str
    visible_in_chat: bool
    profile_tags: tuple[str, ...]
    sort_order: int
