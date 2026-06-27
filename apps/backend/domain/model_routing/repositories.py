"""Repository ports for model routing."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.model_routing.entities import ModelRoute
from apps.backend.domain.model_routing.value_objects import RoutingProfile


class ModelRouteRepository(Protocol):
    def list_for_profile(self, profile: RoutingProfile) -> list[ModelRoute]: ...

    def save(self, route: ModelRoute) -> ModelRoute: ...
