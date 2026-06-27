"""Infrastructure adapter for setup catalog domain orchestration."""

from __future__ import annotations

from typing import Any

from apps.backend.domain import setup_catalog as domain
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.catalog_chat_llm_service import pick_reachable_catalog_provider
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.embedding_client import (
    _normalized_embedding_base,
    clear_embedding_health_cache,
    embedding_catalog_health,
    probe_embedding_output_dim,
)
from apps.backend.infrastructure.model_catalog_providers import (
    fetch_full_model_catalog,
    fetch_models_for_provider,
    get_provider_spec,
    list_provider_specs,
)
from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache


class _SetupCatalogDeps:
    clear_embedding_health_cache = staticmethod(clear_embedding_health_cache)
    embedding_catalog_health = staticmethod(embedding_catalog_health)
    probe_embedding_output_dim = staticmethod(probe_embedding_output_dim)
    pick_reachable_catalog_provider = staticmethod(pick_reachable_catalog_provider)
    fetch_full_model_catalog = staticmethod(fetch_full_model_catalog)
    fetch_models_for_provider = staticmethod(fetch_models_for_provider)
    get_provider_spec = staticmethod(get_provider_spec)
    list_provider_specs = staticmethod(list_provider_specs)
    invalidate_model_catalog_cache = staticmethod(invalidate_model_catalog_cache)
    normalize_external_llm_base_url = staticmethod(operator_settings.normalize_external_llm_base_url)
    operator_provider_endpoints_sync = staticmethod(db.operator_provider_endpoints_sync)
    normalized_embedding_base = staticmethod(_normalized_embedding_base)

    @staticmethod
    def apply_operator_settings_patch(patch: dict[str, Any]) -> None:
        operator_settings.apply_operator_settings_patch(operator_settings.OperatorSettingsPatch(**patch))

    @staticmethod
    def invalidate_operator_settings_cache() -> None:
        operator_settings.invalidate_operator_settings_cache()


domain.register_setup_catalog_dependencies(_SetupCatalogDeps())

SetupPreferencesBody = domain.SetupPreferencesBody
apply_enable_chat_provider_embedding = domain.apply_enable_chat_provider_embedding
apply_setup_preferences = domain.apply_setup_preferences
apply_setup_skip_suggestions = domain.apply_setup_skip_suggestions
build_setup_catalog = domain.build_setup_catalog
test_embedding_model = domain.test_embedding_model
