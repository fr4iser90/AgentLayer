"""Infrastructure adapter for setup catalog domain orchestration."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.setup import catalog as domain
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.agent_runtime.catalog_chat_llm_service import pick_reachable_catalog_provider
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.providers.embedding_client import (
    _normalized_embedding_base,
    clear_embedding_health_cache,
    embedding_catalog_health,
    probe_embedding_output_dim,
)
from apps.backend.infrastructure.providers.model_catalog_providers import (
    fetch_full_model_catalog,
    fetch_models_for_provider,
    get_provider_spec,
    list_provider_specs,
    parse_db_catalog_provider_id,
)
from apps.backend.infrastructure.providers.model_catalog_routing import invalidate_model_catalog_cache
from apps.backend.infrastructure.providers.operator_provider_upsert import (
    collapse_duplicate_operator_provider_endpoints,
    provider_endpoint_dedupe_key,
    upsert_operator_provider_endpoint_by_base_url,
)


def _setup_voice_summary() -> dict[str, Any]:
    """STT/TTS endpoint hints for the setup wizard (non-secret)."""
    import logging

    from apps.backend.infrastructure.settings.operator_settings import _cached_row
    from apps.backend.infrastructure.voice.voice_catalog_providers import (
        list_voice_stt_provider_specs,
        list_voice_tts_provider_specs,
    )

    log = logging.getLogger(__name__)
    stt: list[dict[str, Any]] = []
    tts: list[dict[str, Any]] = []
    try:
        row = _cached_row()
        for spec in list_voice_stt_provider_specs():
            stt.append(
                {
                    "provider_id": getattr(spec, "provider_id", "") or "",
                    "label": getattr(spec, "label", None) or getattr(spec, "provider_id", ""),
                    "source": getattr(spec, "source", "") or "",
                }
            )
        for spec in list_voice_tts_provider_specs():
            tts.append(
                {
                    "provider_id": getattr(spec, "provider_id", "") or "",
                    "label": getattr(spec, "label", None) or getattr(spec, "provider_id", ""),
                    "source": getattr(spec, "source", "") or "",
                }
            )
        return {
            "stt_providers": stt,
            "tts_providers": tts,
            "voice_enabled": bool(row.get("voice_enabled", False)),
            "voice_stt_provider_id": row.get("voice_stt_provider_id"),
            "voice_tts_provider_id": row.get("voice_tts_provider_id"),
            "voice_stt_model": row.get("voice_stt_model"),
            "voice_tts_model": row.get("voice_tts_model"),
        }
    except Exception:
        log.exception("setup catalog voice summary failed")
        return {
            "stt_providers": [],
            "tts_providers": [],
            "voice_enabled": False,
            "voice_stt_provider_id": None,
            "voice_tts_provider_id": None,
            "voice_stt_model": None,
            "voice_tts_model": None,
        }


def _setup_external_runtime_summary() -> dict[str, Any]:
    import logging

    from apps.backend.domain.agent_runtime.external_runtime import available_external_runtimes
    from apps.backend.infrastructure.agent_runtime.external_runtimes.coding_runtime_packages import (
        list_coding_runtime_package_status,
    )
    from apps.backend.infrastructure.platform.config_external_runtimes import (
        DSH_RUNTIME_ENABLED,
        EXTERNAL_RUNTIME_ENABLED,
        QWEN_RUNTIME_ENABLED,
        dsh_runtime_enabled_effective,
        external_runtime_enabled_effective,
        preferred_coding_runtime_effective,
        qwen_runtime_enabled_effective,
    )
    from apps.backend.infrastructure.settings.operator_settings_readers import (
        dsh_runtime_enabled_override,
        external_runtime_enabled_override,
        preferred_coding_runtime_override,
        qwen_runtime_enabled_override,
    )

    log = logging.getLogger(__name__)
    try:
        return {
            "enabled": external_runtime_enabled_effective(),
            "env_enabled": bool(EXTERNAL_RUNTIME_ENABLED),
            "db_override": external_runtime_enabled_override(),
            "qwen_enabled": qwen_runtime_enabled_effective(),
            "qwen_env_enabled": bool(QWEN_RUNTIME_ENABLED),
            "qwen_db_override": qwen_runtime_enabled_override(),
            "dsh_enabled": dsh_runtime_enabled_effective(),
            "dsh_env_enabled": bool(DSH_RUNTIME_ENABLED),
            "dsh_db_override": dsh_runtime_enabled_override(),
            "preferred_id": preferred_coding_runtime_effective(),
            "preferred_db_override": preferred_coding_runtime_override(),
            "packages": list_coding_runtime_package_status(),
            "runtimes": available_external_runtimes(),
        }
    except Exception:
        log.exception("setup catalog external runtime summary failed")
        return {
            "enabled": False,
            "env_enabled": False,
            "db_override": None,
            "qwen_enabled": False,
            "qwen_env_enabled": False,
            "qwen_db_override": None,
            "dsh_enabled": False,
            "dsh_env_enabled": False,
            "dsh_db_override": None,
            "preferred_id": None,
            "preferred_db_override": None,
            "packages": [],
            "runtimes": [],
        }


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
    setup_voice_summary = staticmethod(_setup_voice_summary)
    setup_external_runtime_summary = staticmethod(_setup_external_runtime_summary)
    operator_provider_endpoints_list_all = staticmethod(db.operator_provider_endpoints_list_all)
    parse_db_catalog_provider_id = staticmethod(parse_db_catalog_provider_id)
    provider_endpoint_dedupe_key = staticmethod(provider_endpoint_dedupe_key)
    collapse_duplicate_operator_provider_endpoints = staticmethod(
        collapse_duplicate_operator_provider_endpoints
    )
    upsert_operator_provider_endpoint_by_base_url = staticmethod(
        upsert_operator_provider_endpoint_by_base_url
    )

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
