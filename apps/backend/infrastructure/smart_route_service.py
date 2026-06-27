"""Infrastructure adapter for domain smart LLM routing."""

from __future__ import annotations

from apps.backend.domain import llm_smart_route as domain
from apps.backend.infrastructure.catalog_llm_client import post_catalog_chat_completions
from apps.backend.infrastructure.model_catalog_providers import get_provider_spec
from apps.backend.infrastructure.operator_settings import smart_routing_params


class _SmartRouteDeps:
    smart_routing_params = staticmethod(smart_routing_params)
    post_catalog_chat_completions = staticmethod(post_catalog_chat_completions)

    @staticmethod
    def catalog_provider_exists(provider_id: str) -> bool:
        return get_provider_spec(provider_id) is not None


domain.register_smart_route_dependencies(_SmartRouteDeps())
