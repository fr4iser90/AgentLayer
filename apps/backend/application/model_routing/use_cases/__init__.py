"""Model routing use cases."""
from __future__ import annotations

from apps.backend.application.model_routing.commands import SaveModelRouteCommand
from apps.backend.application.model_routing.dtos import ModelRouteDto
from apps.backend.application.model_routing.ports import ModelRouteRepository
from apps.backend.application.model_routing.queries import ListModelRoutesQuery
from apps.backend.domain.model_routing.entities import ModelRoute
from apps.backend.domain.model_routing.schemas import validate_routing_priority, validate_routing_provider
from apps.backend.domain.model_routing.value_objects import ModelId, RoutingProfile


def _to_dto(route: ModelRoute) -> ModelRouteDto:
    return ModelRouteDto(
        profile=route.profile.value,
        model_id=route.model_id.value,
        provider=route.provider,
        priority=route.priority,
    )


def list_model_routes(repo: ModelRouteRepository, query: ListModelRoutesQuery) -> list[ModelRouteDto]:
    return [_to_dto(item) for item in repo.list_for_profile(RoutingProfile.parse(query.profile))]


def save_model_route(repo: ModelRouteRepository, command: SaveModelRouteCommand) -> ModelRouteDto:
    route = ModelRoute(
        profile=RoutingProfile.parse(command.profile),
        model_id=ModelId.parse(command.model_id),
        provider=validate_routing_provider(command.provider),
        priority=validate_routing_priority(command.priority),
    )
    return _to_dto(repo.save(route))
