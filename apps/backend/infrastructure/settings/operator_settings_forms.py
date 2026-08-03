from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

class OperatorSettingsPayload(BaseModel):
    """Full replace on PUT (empty strings clear optional fields where applicable)."""

    discord_application_id: str = Field(default="", max_length=128)
    integration_notes: str = Field(default="", max_length=8000)


class OperatorSettingsPatch(BaseModel):
    """Partial update (PATCH). Omitted fields are left unchanged; JSON null clears secrets."""

    model_config = ConfigDict(extra="forbid")

    discord_application_id: str | None = Field(default=None, max_length=128)
    integration_notes: str | None = Field(default=None, max_length=8000)
    discord_bot_enabled: bool | None = None
    discord_bot_token: str | None = Field(default=None, max_length=256)
    discord_trigger_prefix: str | None = Field(default=None, max_length=64)
    discord_chat_model: str | None = Field(default=None, max_length=256)
    discord_chat_model_catalog_owned_by: str | None = Field(default=None, max_length=64)
    telegram_bot_enabled: bool | None = None
    telegram_bot_token: str | None = Field(default=None, max_length=256)
    telegram_trigger_prefix: str | None = Field(default=None, max_length=64)
    telegram_chat_model: str | None = Field(default=None, max_length=256)
    telegram_chat_model_catalog_owned_by: str | None = Field(default=None, max_length=64)
    dashboard_upload_max_file_mb: int | None = None
    dashboard_upload_allowed_mime: str | None = Field(default=None, max_length=2000)
    llm_smart_routing_enabled: bool | None = None
    llm_router_model: str | None = Field(default=None, max_length=128)
    llm_router_model_catalog_owned_by: str | None = Field(default=None, max_length=64)
    llm_router_local_confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_router_timeout_sec: float | None = Field(default=None, ge=1.0, le=120.0)
    llm_route_long_prompt_chars: int | None = Field(default=None, ge=100, le=500000)
    llm_route_short_local_max_chars: int | None = Field(default=None, ge=1, le=50000)
    llm_route_many_code_fences: int | None = Field(default=None, ge=1, le=100)
    llm_route_many_messages: int | None = Field(default=None, ge=1, le=500)
    llm_queue_policy: str | None = Field(default=None, max_length=32)
    llm_queue_user_priority: int | None = Field(default=None, ge=0, le=1000)
    llm_queue_benchmark_priority: int | None = Field(default=None, ge=0, le=1000)
    llm_queue_scheduler_priority: int | None = Field(default=None, ge=0, le=1000)
    delegate_enabled: bool | None = None
    deployment_mode: str | None = Field(default=None, max_length=32)
    memory_graph_enabled: bool | None = None
    memory_graph_max_hops: int | None = Field(default=None, ge=0, le=4)
    memory_graph_min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    memory_graph_max_bullets: int | None = Field(default=None, ge=1, le=50)
    memory_graph_max_prompt_chars: int | None = Field(default=None, ge=200, le=50000)
    memory_graph_log_activations: bool | None = None
    memory_enabled: bool | None = None
    rag_enabled: bool | None = None
    rag_embedding_model: str | None = Field(default=None, max_length=256)
    rag_embedding_dim: int | None = Field(default=None, ge=32, le=4096)
    embedding_api_base_url: str | None = Field(default=None, max_length=2048)
    embedding_api_key: str | None = Field(default=None, max_length=4096)
    embedding_api_header_name: str | None = Field(default=None, max_length=128)
    rag_embedding_provider_id: str | None = Field(default=None, max_length=64)
    extractor_api_base_url: str | None = Field(default=None, max_length=2048)
    extractor_api_key: str | None = Field(default=None, max_length=4096)
    extractor_api_header_name: str | None = Field(default=None, max_length=128)
    extractor_provider_id: str | None = Field(default=None, max_length=64)
    extractor_model: str | None = Field(default=None, max_length=256)
    extractor_timeout_sec: float | None = Field(default=None, ge=1.0, le=1800.0)
    rag_chunk_size: int | None = Field(default=None, ge=200, le=8000)
    rag_chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    rag_top_k: int | None = Field(default=None, ge=1, le=50)
    rag_embed_timeout_sec: float | None = Field(default=None, ge=5.0, le=600.0)
    rag_tenant_shared_domains: str | None = Field(default=None, max_length=4000)
    docs_root: str | None = Field(default=None, max_length=4096)
    pidea_enabled: bool | None = None
    pidea_cdp_http_url: str | None = Field(default=None, max_length=512)
    pidea_selector_ide: str | None = Field(default=None, max_length=32)
    pidea_selector_version: str | None = Field(default=None, max_length=64)
    expose_internal_errors: bool | None = None
    http_client_log_level: str | None = Field(default=None, max_length=16)
    scheduler_enabled: bool | None = None
    scheduler_interval_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    scheduler_user_id: str | None = Field(default=None, max_length=64)
    scheduler_model: str | None = Field(default=None, max_length=256)
    scheduler_max_tool_rounds: int | None = Field(default=None, ge=1, le=64)
    scheduler_notify_only_if_not_ok: bool | None = None
    scheduler_max_outbound_per_day: int | None = Field(default=None, ge=0, le=100_000)
    scheduler_allowed_tool_packages: str | None = Field(default=None, max_length=4000)
    scheduler_llm_backend: str | None = Field(default=None, max_length=16)
    scheduler_tools_mode: str | None = Field(default=None, max_length=16)
    scheduler_pidea_enabled: bool | None = None
    scheduler_instructions: str | None = Field(default=None, max_length=32000)
    scheduler_jobs_worker_enabled: bool | None = None
    scheduler_jobs_ide_pidea_enabled: bool | None = None
    scheduler_jobs_ide_pidea_timeout_sec: float | None = Field(default=None, ge=30.0, le=900.0)
    workspace_allow_self_editing: bool | None = None
    workspace_index_on_write_default: str | None = Field(default=None, max_length=16)
    workspace_reindex_after_git_pull: bool | None = None
    workspace_nightly_reindex_enabled: bool | None = None
    workspace_index_on_attach_enabled: bool | None = None
    media_library_enabled: bool | None = None
    media_user_upload_enabled: bool | None = None
    media_sharing_enabled: bool | None = None
    media_default_user_quota_mb: int | None = Field(default=None, ge=1, le=50_000)
    media_upload_max_file_mb: int | None = Field(default=None, ge=1, le=512)
    media_upload_allowed_mime: str | None = Field(default=None, max_length=2000)
    media_embed_allowed_hosts: str | None = Field(default=None, max_length=4000)
    voice_enabled: bool | None = None
    voice_provider_id: str | None = Field(default=None, max_length=64)
    voice_stt_provider_id: str | None = Field(default=None, max_length=64)
    voice_tts_provider_id: str | None = Field(default=None, max_length=64)
    voice_api_base_url: str | None = Field(default=None, max_length=2048)
    voice_api_key: str | None = Field(default=None, max_length=4096)
    voice_stt_model: str | None = Field(default=None, max_length=128)
    voice_tts_model: str | None = Field(default=None, max_length=128)
    voice_tts_voice: str | None = Field(default=None, max_length=64)
    voice_max_seconds: int | None = Field(default=None, ge=5, le=600)
    voice_max_bytes: int | None = Field(default=None, ge=64_000, le=52_428_800)
    voice_bridge_telegram: bool | None = None
    voice_bridge_discord: bool | None = None
    voice_realtime_enabled: bool | None = None
    voice_discord_vc_enabled: bool | None = None
    legal_enabled: bool | None = None
    legal_jurisdiction: str | None = Field(default=None, max_length=16)
    legal_entity_name: str | None = Field(default=None, max_length=256)
    legal_entity_address: str | None = Field(default=None, max_length=4000)
    legal_entity_email: str | None = Field(default=None, max_length=256)
    legal_entity_phone: str | None = Field(default=None, max_length=64)
    legal_terms_enabled: bool | None = None
    legal_impressum_md: str | None = Field(default=None, max_length=200_000)
    legal_privacy_md: str | None = Field(default=None, max_length=200_000)
    legal_terms_md: str | None = Field(default=None, max_length=200_000)


def operator_settings_patch_field_names() -> tuple[str, ...]:
    """Patchable operator_settings keys (single source of truth: ``OperatorSettingsPatch``)."""
    return tuple(OperatorSettingsPatch.model_fields.keys())


def operator_settings_patch_tool_parameters() -> dict[str, Any]:
    """OpenAI ``tools[]`` parameters object generated from ``OperatorSettingsPatch``."""
    schema = OperatorSettingsPatch.model_json_schema()
    props = schema.get("properties")
    if not isinstance(props, dict):
        props = {}
    return {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
        "minProperties": 1,
    }


def operator_settings_patch_client_error(
    error: str,
    *,
    reason: str = "invalid_arguments",
) -> dict[str, Any]:
    """Minimal tool error for ``settings_patch`` — no hints; use settings_get / get_tool_help separately."""
    return {"ok": False, "error": error, "reason": reason}

