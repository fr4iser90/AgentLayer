"""Provider aggregate entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.backend.domain.providers.schemas import (
    validate_api_header_name,
    validate_api_key,
    validate_max_parallel,
    validate_model_id,
    validate_provider_base_url,
    validate_provider_options,
)
from apps.backend.domain.providers.value_objects import ProviderId, ProviderKind, ProviderLabel, normalize_provider_kind


@dataclass(slots=True)
class ProviderEndpoint:
    provider_id: ProviderId
    kind: ProviderKind
    label: ProviderLabel
    base_url: str
    enabled: bool = True
    api_header_name: str = "Authorization"
    api_key: str | None = None
    model_default: str | None = None
    max_parallel: int = 1
    options: dict[str, Any] = field(default_factory=dict)
    db_id: int | None = None

    def __post_init__(self) -> None:
        self.kind = normalize_provider_kind(self.kind)
        self.base_url = validate_provider_base_url(self.base_url)
        self.api_header_name = validate_api_header_name(self.api_header_name)
        self.api_key = validate_api_key(self.api_key)
        self.model_default = validate_model_id(self.model_default)
        self.max_parallel = validate_max_parallel(self.max_parallel)
        self.options = validate_provider_options(self.options)


@dataclass(frozen=True, slots=True)
class ModelCatalogPreference:
    provider_id: ProviderId
    model_id: str
    visible_in_chat: bool = True
    profile_tags: tuple[str, ...] = ()
    sort_order: int = 0

    def __post_init__(self) -> None:
        model_id = validate_model_id(self.model_id)
        if model_id is None:
            raise ValueError("model_id is required")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(
            self,
            "profile_tags",
            tuple(str(tag).strip() for tag in self.profile_tags if str(tag).strip()),
        )
