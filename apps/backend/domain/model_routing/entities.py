"""Model routing entities."""
from __future__ import annotations

from dataclasses import dataclass

from apps.backend.domain.model_routing.value_objects import ModelId, RoutingProfile


@dataclass(frozen=True, slots=True)
class ModelRoute:
    profile: RoutingProfile
    model_id: ModelId
    provider: str
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("model route provider must not be blank")
        if self.priority < 0:
            raise ValueError("model route priority must be non-negative")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    selected: ModelRoute
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("routing decision reason must not be blank")
