import type { ModelRow } from "../../../lib/modelCatalog";

export function envProviderPatternFromCleanupKeys(cleanupKeys: string[] | undefined): string {
  const first = (cleanupKeys ?? []).find((key) => /_\d+_/.test(key));
  if (!first) return "env provider";
  return first.replace(/_\d+_.*/, "_N_*");
}

export type InterfaceHints = {
  discord_application_id: string;
  telegram_application_id?: string;
  agent_mode?: "" | "sandbox" | "host";
  agent_mode_effective?: "sandbox" | "host";
  agent_mode_env?: "sandbox" | "host";
};

export type OperatorPublic = {
  discord_bot_enabled?: boolean;
  discord_bot_token_configured?: boolean;
  discord_trigger_prefix?: string;
  discord_chat_model?: string;
  discord_chat_model_catalog_owned_by?: string | null;
  telegram_bot_enabled?: boolean;
  telegram_bot_token_configured?: boolean;
  telegram_trigger_prefix?: string;
  telegram_chat_model?: string;
  telegram_chat_model_catalog_owned_by?: string | null;
  dashboard_upload_max_file_mb?: number | null;
  dashboard_upload_allowed_mime?: string;
  dashboard_upload_effective_max_bytes?: number;
  dashboard_upload_effective_allowed_mime?: string[];
  llm_smart_routing_enabled?: boolean;
  llm_router_model?: string;
  llm_router_model_catalog_owned_by?: string | null;
  llm_router_local_confidence_min?: number;
  llm_router_timeout_sec?: number;
  llm_route_long_prompt_chars?: number;
  llm_route_short_local_max_chars?: number;
  llm_route_many_code_fences?: number;
  llm_route_many_messages?: number;
  llm_queue_policy?: "fifo" | "priority" | "round_robin";
  llm_queue_user_priority?: number;
  llm_queue_benchmark_priority?: number;
  llm_queue_scheduler_priority?: number;
  memory_graph_enabled?: boolean;
  memory_graph_max_hops?: number;
  memory_graph_min_score?: number;
  memory_graph_max_bullets?: number;
  memory_graph_max_prompt_chars?: number;
  memory_graph_log_activations?: boolean;
  memory_enabled?: boolean;
  rag_enabled?: boolean;
  /** DB-stored OpenAI-compatible embedding base (env ``EMBEDDING_PROVIDER_N_*`` wins when configured). */
  embedding_api_base_url?: string | null;
  embedding_api_base_source?: "env" | "operator_settings" | null;
  embedding_api_base_effective?: string | null;
  embedding_api_key_configured?: boolean;
  embedding_api_key_source?: "env" | "operator_settings" | null;
  embedding_api_header_name?: string | null;
  embedding_api_header_name_effective?: string | null;
  embedding_api_header_name_source?: "env" | "operator_settings" | null;
  rag_embedding_provider_id?: string | null;
  rag_embedding_provider_id_effective?: string | null;
  rag_embedding_provider_id_source?: "operator_settings" | null;
  embedding_providers?: Array<{
    provider_id: string;
    label: string;
    source: string;
    base_url: string;
  }>;
  extractor_provider_configured?: boolean;
  extractor_api_base_url?: string | null;
  extractor_api_base_effective?: string | null;
  extractor_api_key_configured?: boolean;
  extractor_api_header_name?: string | null;
  extractor_api_header_name_effective?: string | null;
  extractor_provider_id?: string | null;
  extractor_provider_id_effective?: string | null;
  extractor_model?: string;
  extractor_timeout_sec?: number;
  extractor_providers?: Array<{
    provider_id: string;
    label: string;
    source: string;
    base_url: string;
    model_default?: string | null;
    timeout_sec?: number;
  }>;
  rag_embedding_model?: string;
  rag_embedding_dim?: number;
  rag_chunk_size?: number;
  rag_chunk_overlap?: number;
  rag_top_k?: number;
  rag_embed_timeout_sec?: number;
  rag_tenant_shared_domains?: string;
  rag_tenant_shared_domains_effective?: string[];
  docs_root?: string;
  expose_internal_errors?: boolean;
  http_client_log_level?: string;
  scheduler_enabled?: boolean;
  scheduler_interval_minutes?: number;
  scheduler_user_id?: string;
  scheduler_model?: string | null;
  scheduler_max_tool_rounds?: number | null;
  scheduler_notify_only_if_not_ok?: boolean;
  scheduler_max_outbound_per_day?: number;
  scheduler_allowed_tool_packages?: string;
  scheduler_llm_backend?: string;
  scheduler_tools_mode?: string;
  scheduler_pidea_enabled?: boolean;
  scheduler_instructions?: string;
  scheduler_jobs_worker_enabled?: boolean;
  scheduler_jobs_ide_pidea_enabled?: boolean;
  scheduler_jobs_ide_pidea_timeout_sec?: number;
  workspace_allow_self_editing?: boolean;
  workspace_index_on_write_default?: string;
  workspace_reindex_after_git_pull?: boolean;
  workspace_nightly_reindex_enabled?: boolean;
  workspace_index_on_attach_enabled?: boolean;
  media_library_enabled?: boolean;
  media_user_upload_enabled?: boolean;
  media_sharing_enabled?: boolean;
  media_default_user_quota_mb?: number | null;
  media_upload_max_file_mb?: number | null;
  media_upload_allowed_mime?: string;
  media_embed_allowed_hosts?: string;
  media_effective_upload_max_bytes?: number;
  media_effective_upload_allowed_mime?: string[];
  media_effective_default_quota_mb?: number;
  voice_enabled?: boolean;
  voice_api_base_url?: string;
  voice_api_base_source?: "env" | "operator_settings" | null;
  voice_api_base_effective?: string | null;
  voice_api_key_configured?: boolean;
  voice_api_key_source?: "env" | "operator_settings" | null;
  voice_stt_provider_id?: string | null;
  voice_stt_provider_id_effective?: string | null;
  voice_stt_provider_id_source?: "operator_settings" | null;
  voice_tts_provider_id?: string | null;
  voice_tts_provider_id_effective?: string | null;
  voice_tts_provider_id_source?: "operator_settings" | null;
  voice_stt_api_base_effective?: string | null;
  voice_tts_api_base_effective?: string | null;
  voice_stt_providers?: Array<{ provider_id: string; label: string; source: string; base_url: string; role?: string }>;
  voice_tts_providers?: Array<{ provider_id: string; label: string; source: string; base_url: string; role?: string }>;
  voice_providers?: Array<{ provider_id: string; label: string; source: string; base_url: string; role?: string }>;
  voice_stt_model?: string;
  voice_tts_model?: string;
  voice_tts_voice?: string;
  voice_max_seconds?: number;
  voice_max_bytes?: number;
  voice_bridge_telegram?: boolean;
  voice_bridge_discord?: boolean;
  voice_realtime_enabled?: boolean;
  voice_discord_vc_enabled?: boolean;
  detail?: unknown;
};

export type ExternalLlmEndpointUI = {
  localKey: string;
  id: number | null;
  enabled: boolean;
  label: string;
  baseUrl: string;
  apiKey: string;
  apiKeyConfigured: boolean;
  apiHeaderName: string;
  modelDefault: string;
  modelVlm: string;
  modelAgent: string;
  modelCoding: string;
  maxParallel: number;
};

export type EnvLlmProviderPreview = {
  index: number;
  provider_id: string;
  label: string;
  base_url: string;
  api_key_configured: boolean;
  api_key_last4?: string | null;
  api_header_name: string;
  model_default?: string | null;
  model_vlm?: string | null;
  model_agent?: string | null;
  model_coding?: string | null;
  max_parallel: number;
  cleanup_keys: string[];
  already_in_db: boolean;
  matched_db_endpoint_id?: number | null;
};

export type EnvLlmProvidersPayload = {
  providers?: EnvLlmProviderPreview[];
  count?: number;
  cleanup_note?: string;
  detail?: unknown;
};

export type OperatorEnvProviderPreview = {
  kind: string;
  index: number;
  provider_id: string;
  label: string;
  base_url: string;
  api_key_configured: boolean;
  api_key_last4?: string | null;
  api_header_name: string;
  model_default?: string | null;
  options_json?: Record<string, unknown>;
  cleanup_keys: string[];
  already_in_db: boolean;
  matched_db_endpoint_id?: number | null;
};

export type OperatorEnvProvidersPayload = {
  providers?: OperatorEnvProviderPreview[];
  count?: number;
  cleanup_note?: string;
  detail?: unknown;
};

export type OperatorProviderEndpointUI = {
  id: number | null;
  kind: string;
  providerId: string;
  source?: string;
  enabled: boolean;
  label: string;
  baseUrl: string;
  apiKey?: string;
  apiKeyConfigured: boolean;
  apiKeyLast4?: string | null;
  apiHeaderName: string;
  modelDefault: string;
  maxParallel: number;
  optionsJson: Record<string, unknown>;
  models: string[];
  modelsDetail?: string | null;
};

export type OperatorProviderKind = string;

export type OperatorProviderKindMetadata = {
  kind: string;
  capability: string;
  title_i18n_key: string;
  intro_i18n_key: string;
  empty_i18n_key: string;
  model_label_i18n_key?: string | null;
  model_placeholder_i18n_key?: string | null;
  model_setting_key?: string | null;
  env_prefix_pattern?: string | null;
  supports_models?: boolean;
};

export type ModelDefaultProfileMetadata = {
  profile: string;
  capability: string;
  title_i18n_key: string;
  source: "catalog" | "provider_models" | string;
};

export type ModelCatalogPref = {
  provider_id: string;
  model_id: string;
  visible_in_chat: boolean;
  profile_tags?: string[];
  sort_order?: number;
};

export type AdminModelCatalogPayload = {
  data?: ModelRow[];
  prefs?: ModelCatalogPref[];
  detail?: unknown;
};

export function detailMessage(data: unknown): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return JSON.stringify(d);
  }
  return "Request failed";
}
