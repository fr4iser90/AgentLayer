"""Infrastructure adapter for catalog-backed chat LLM domain helpers."""

from __future__ import annotations

from apps.backend.domain import catalog_chat_llm as domain
from apps.backend.infrastructure.model_catalog_providers import (
    fetch_models_for_provider,
    get_provider_spec,
    list_provider_specs,
    resolve_model_for_provider,
)
from apps.backend.infrastructure.model_catalog_routing import infer_catalog_owned_by
from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by


class _CatalogChatLlmDeps:
    infer_catalog_owned_by = staticmethod(infer_catalog_owned_by)
    fetch_models_for_provider = staticmethod(fetch_models_for_provider)
    get_provider_spec = staticmethod(get_provider_spec)
    list_provider_specs = staticmethod(list_provider_specs)
    resolve_model_for_provider = staticmethod(resolve_model_for_provider)
    normalize_model_catalog_owned_by = staticmethod(normalize_model_catalog_owned_by)


domain.register_catalog_chat_llm_dependencies(_CatalogChatLlmDeps())

cached_llm_reachable = domain.cached_llm_reachable
catalog_llm_body_extras = domain.catalog_llm_body_extras
finalize_catalog_chat_llm = domain.finalize_catalog_chat_llm
invalidate_reachable_catalog_cache = domain.invalidate_reachable_catalog_cache
pick_reachable_catalog_provider = domain.pick_reachable_catalog_provider
