import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";
import {
  embeddingModelOptions,
  fetchModelCatalog,
  formatEmbeddingStatusHint,
  type EmbeddingCatalogHealth,
  type ModelRow,
  normalizeCatalogRoutingToken,
} from "../../../lib/modelCatalog";
import {
  type AdminModelCatalogPayload,
  detailMessage,
  type EnvLlmProviderPreview,
  type EnvLlmProvidersPayload,
  type ExternalLlmEndpointUI,
  type InterfaceHints,
  type ModelDefaultProfileMetadata,
  type ModelCatalogPref,
  type OperatorPublic,
  type OperatorEnvProviderPreview,
  type OperatorEnvProvidersPayload,
  type OperatorProviderEndpointUI,
  type OperatorProviderKind,
  type OperatorProviderKindMetadata,
} from "./operatorSettingsTypes";

function useOperatorSettingsState() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const [discordAppId, setDiscordAppId] = useState("");
  const [telegramAppId, setTelegramAppId] = useState("");
  const [agentMode, setAgentMode] = useState<"env" | "sandbox" | "host">("env");
  const [agentModeEnv, setAgentModeEnv] = useState<string>("sandbox");
  const [agentModeEffective, setAgentModeEffective] = useState<string>("sandbox");
  const [bridgeEnabled, setBridgeEnabled] = useState(false);
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [triggerPrefix, setTriggerPrefix] = useState("!agent ");
  const [chatModel, setChatModel] = useState("");
  const [chatModelProvider, setChatModelProvider] = useState("");
  const [discordToken, setDiscordToken] = useState("");
  const [tgBridgeEnabled, setTgBridgeEnabled] = useState(false);
  const [tgTokenConfigured, setTgTokenConfigured] = useState(false);
  const [tgTriggerPrefix, setTgTriggerPrefix] = useState("!agent ");
  const [tgChatModel, setTgChatModel] = useState("");
  const [tgChatModelProvider, setTgChatModelProvider] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [uploadMaxMb, setUploadMaxMb] = useState("");
  const [uploadMime, setUploadMime] = useState("");
  const [uploadEffBytes, setUploadEffBytes] = useState<number | null>(null);
  const [uploadEffMime, setUploadEffMime] = useState<string[]>([]);
  const [mediaLibraryEnabled, setMediaLibraryEnabled] = useState(false);
  const [mediaUserUploadEnabled, setMediaUserUploadEnabled] = useState(false);
  const [mediaSharingEnabled, setMediaSharingEnabled] = useState(false);
  const [mediaDefaultQuotaMb, setMediaDefaultQuotaMb] = useState("");
  const [mediaUploadMaxMb, setMediaUploadMaxMb] = useState("");
  const [mediaUploadMime, setMediaUploadMime] = useState("");
  const [mediaEmbedHosts, setMediaEmbedHosts] = useState("");
  const [mediaEffUploadBytes, setMediaEffUploadBytes] = useState<number | null>(null);
  const [mediaEffUploadMime, setMediaEffUploadMime] = useState<string[]>([]);
  const [mediaEffDefaultQuotaMb, setMediaEffDefaultQuotaMb] = useState<number | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceApiBaseUrl, setVoiceApiBaseUrl] = useState("https://api.openai.com/v1");
  const [voiceApiBaseSource, setVoiceApiBaseSource] = useState<"env" | "operator_settings" | null>(
    null
  );
  const [voiceApiBaseEffective, setVoiceApiBaseEffective] = useState<string | null>(null);
  const [voiceApiKey, setVoiceApiKey] = useState("");
  const [voiceApiKeyConfigured, setVoiceApiKeyConfigured] = useState(false);
  const [voiceApiKeySource, setVoiceApiKeySource] = useState<"env" | "operator_settings" | null>(
    null
  );
  const [voiceSttProviderId, setVoiceSttProviderId] = useState("");
  const [voiceSttProviderIdEffective, setVoiceSttProviderIdEffective] = useState<string | null>(null);
  const [voiceTtsProviderId, setVoiceTtsProviderId] = useState("");
  const [voiceTtsProviderIdEffective, setVoiceTtsProviderIdEffective] = useState<string | null>(null);
  const [voiceSttApiBaseEffective, setVoiceSttApiBaseEffective] = useState<string | null>(null);
  const [voiceTtsApiBaseEffective, setVoiceTtsApiBaseEffective] = useState<string | null>(null);
  const [voiceSttProviders, setVoiceSttProviders] = useState<
    Array<{ provider_id: string; label: string; source: string; base_url: string }>
  >([]);
  const [voiceTtsProviders, setVoiceTtsProviders] = useState<
    Array<{ provider_id: string; label: string; source: string; base_url: string }>
  >([]);
  const [voiceSttModel, setVoiceSttModel] = useState("whisper-1");
  const [voiceTtsModel, setVoiceTtsModel] = useState("tts-1");
  const [voiceTtsVoice, setVoiceTtsVoice] = useState("alloy");
  const [voiceBridgeTelegram, setVoiceBridgeTelegram] = useState(true);
  const [voiceBridgeDiscord, setVoiceBridgeDiscord] = useState(true);
  const [voiceRealtimeEnabled, setVoiceRealtimeEnabled] = useState(false);
  const [voiceDiscordVcEnabled, setVoiceDiscordVcEnabled] = useState(false);
  const [extLlmEndpoints, setExtLlmEndpoints] = useState<ExternalLlmEndpointUI[]>([]);
  const [llmSmartRouting, setLlmSmartRouting] = useState(false);
  const [llmRouterModel, setLlmRouterModel] = useState("");
  const [llmRouterModelProvider, setLlmRouterModelProvider] = useState("");
  const [llmRouterConfMin, setLlmRouterConfMin] = useState("0.7");
  const [llmRouterTimeoutSec, setLlmRouterTimeoutSec] = useState("12");
  const [llmRouteLongChars, setLlmRouteLongChars] = useState("8000");
  const [llmRouteShortChars, setLlmRouteShortChars] = useState("220");
  const [llmRouteManyFences, setLlmRouteManyFences] = useState("3");
  const [llmRouteManyMsgs, setLlmRouteManyMsgs] = useState("14");
  const [llmQueuePolicy, setLlmQueuePolicy] = useState<"fifo" | "priority" | "round_robin">("priority");
  const [llmQueueUserPriority, setLlmQueueUserPriority] = useState("100");
  const [llmQueueBenchmarkPriority, setLlmQueueBenchmarkPriority] = useState("10");
  const [llmQueueSchedulerPriority, setLlmQueueSchedulerPriority] = useState("50");
  const [memGraphEnabled, setMemGraphEnabled] = useState(true);
  const [memGraphMaxHops, setMemGraphMaxHops] = useState("2");
  const [memGraphMinScore, setMemGraphMinScore] = useState("0.03");
  const [memGraphMaxBullets, setMemGraphMaxBullets] = useState("14");
  const [memGraphMaxPromptChars, setMemGraphMaxPromptChars] = useState("3500");
  const [memGraphLogActivations, setMemGraphLogActivations] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [embeddingApiBaseUrl, setEmbeddingApiBaseUrl] = useState("");
  const [embeddingApiBaseSource, setEmbeddingApiBaseSource] = useState<
    "env" | "operator_settings" | null
  >(null);
  const [embeddingApiBaseEffective, setEmbeddingApiBaseEffective] = useState<string | null>(null);
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [embeddingApiKeyConfigured, setEmbeddingApiKeyConfigured] = useState(false);
  const [embeddingApiKeySource, setEmbeddingApiKeySource] = useState<
    "env" | "operator_settings" | null
  >(null);
  const [embeddingApiHeaderName, setEmbeddingApiHeaderName] = useState("X-API-KEY");
  const [embeddingApiHeaderNameEffective, setEmbeddingApiHeaderNameEffective] = useState("X-API-KEY");
  const [embeddingApiHeaderNameSource, setEmbeddingApiHeaderNameSource] = useState<
    "env" | "operator_settings" | null
  >(null);
  const [ragEmbeddingModel, setRagEmbeddingModel] = useState("");
  const [ragEmbeddingModelOptions, setRagEmbeddingModelOptions] = useState<string[]>([]);
  const [ragEmbeddingStatusHint, setRagEmbeddingStatusHint] = useState<string | null>(null);
  const [embeddingModelsLoading, setEmbeddingModelsLoading] = useState(false);
  const [ragEmbeddingProviderId, setRagEmbeddingProviderId] = useState("");
  const [ragEmbeddingProviderIdEffective, setRagEmbeddingProviderIdEffective] = useState<string | null>(null);
  const [ragEmbeddingProviderIdSource, setRagEmbeddingProviderIdSource] = useState<
    "operator_settings" | null
  >(null);
  const [embeddingProviders, setEmbeddingProviders] = useState<
    Array<{ provider_id: string; label: string; source: string; base_url: string }>
  >([]);
  const [extractorProviders, setExtractorProviders] = useState<
    Array<{
      provider_id: string;
      label: string;
      source: string;
      base_url: string;
      model_default?: string | null;
      timeout_sec?: number;
    }>
  >([]);
  const [extractorApiBaseUrl, setExtractorApiBaseUrl] = useState("");
  const [extractorApiBaseEffective, setExtractorApiBaseEffective] = useState<string | null>(null);
  const [extractorApiKey, setExtractorApiKey] = useState("");
  const [extractorApiKeyConfigured, setExtractorApiKeyConfigured] = useState(false);
  const [extractorApiHeaderName, setExtractorApiHeaderName] = useState("X-API-KEY");
  const [extractorApiHeaderNameEffective, setExtractorApiHeaderNameEffective] = useState("X-API-KEY");
  const [extractorProviderId, setExtractorProviderId] = useState("");
  const [extractorProviderIdEffective, setExtractorProviderIdEffective] = useState<string | null>(null);
  const [extractorModel, setExtractorModel] = useState("");
  const [extractorTimeoutSec, setExtractorTimeoutSec] = useState("120");
  const [ragEmbeddingDim, setRagEmbeddingDim] = useState("768");
  const [ragChunkSize, setRagChunkSize] = useState("1200");
  const [ragChunkOverlap, setRagChunkOverlap] = useState("200");
  const [ragTopK, setRagTopK] = useState("8");
  const [ragEmbedTimeout, setRagEmbedTimeout] = useState("120");
  const [ragTenantDomains, setRagTenantDomains] = useState("agentlayer_docs,tenant_knowledge");
  const [ragTenantEffective, setRagTenantEffective] = useState<string[]>([]);
  const [docsRoot, setDocsRoot] = useState("");
  const [exposeInternalErrors, setExposeInternalErrors] = useState(false);
  const [httpClientLogLevel, setHttpClientLogLevel] = useState("WARNING");
  const [schedulerEnabled, setSchedulerEnabled] = useState(false);
  const [schedulerIntervalMin, setSchedulerIntervalMin] = useState("60");
  const [schedulerUserId, setSchedulerUserId] = useState("");
  const [schedulerModel, setSchedulerModel] = useState("");
  const [schedulerMaxRounds, setSchedulerMaxRounds] = useState("");
  const [schedulerNotifyOnlyIfNotOk, setSchedulerNotifyOnlyIfNotOk] = useState(true);
  const [schedulerMaxOutbound, setSchedulerMaxOutbound] = useState("10");
  const [schedulerPackages, setSchedulerPackages] = useState("");
  const [schedulerLlmBackend, setSchedulerLlmBackend] = useState("inherit");
  const [schedulerToolsMode, setSchedulerToolsMode] = useState("none");
  const [schedulerInstructions, setSchedulerInstructions] = useState("");
  const [schedulerJobsWorkerEnabled, setSchedulerJobsWorkerEnabled] = useState(true);
  const [workspaceAllowSelfEditing, setWorkspaceAllowSelfEditing] = useState(false);
  const [workspaceIndexOnWriteDefault, setWorkspaceIndexOnWriteDefault] = useState("debounced");
  const [workspaceReindexAfterGitPull, setWorkspaceReindexAfterGitPull] = useState(false);
  const [workspaceNightlyReindexEnabled, setWorkspaceNightlyReindexEnabled] = useState(false);
  const [workspaceIndexOnAttachEnabled, setWorkspaceIndexOnAttachEnabled] = useState(false);
  const [adminUsers, setAdminUsers] = useState<Array<{ id: string; email?: string | null; display_name?: string | null }>>([]);
  const [extLlmModelIds, setExtLlmModelIds] = useState<string[]>([]);
  const [extLlmModelsLoading, setExtLlmModelsLoading] = useState(false);
  const [extLlmModelsHint, setExtLlmModelsHint] = useState<string | null>(null);
  const [envLlmProviders, setEnvLlmProviders] = useState<EnvLlmProviderPreview[]>([]);
  const [envLlmCleanupNote, setEnvLlmCleanupNote] = useState<string | null>(null);
  const [envLlmImporting, setEnvLlmImporting] = useState(false);
  const [envOperatorProviders, setEnvOperatorProviders] = useState<
    Record<OperatorProviderKind, OperatorEnvProviderPreview[]>
  >({});
  const [operatorProviderEndpoints, setOperatorProviderEndpoints] = useState<
    Record<OperatorProviderKind, OperatorProviderEndpointUI[]>
  >({});
  const [operatorProviderDeleteIds, setOperatorProviderDeleteIds] = useState<
    Record<OperatorProviderKind, number[]>
  >({});
  const [envOperatorCleanupNotes, setEnvOperatorCleanupNotes] = useState<
    Record<OperatorProviderKind, string | null>
  >({});
  const [operatorProviderKindMetadata, setOperatorProviderKindMetadata] = useState<OperatorProviderKindMetadata[]>([]);
  const [modelDefaultProfileMetadata, setModelDefaultProfileMetadata] = useState<ModelDefaultProfileMetadata[]>([]);
  const [envOperatorImporting, setEnvOperatorImporting] = useState<OperatorProviderKind | null>(null);
  const [operatorProviderModelOptions, setOperatorProviderModelOptions] = useState<Record<string, string[]>>({});
  const [operatorProviderModelsLoading, setOperatorProviderModelsLoading] = useState<Record<string, boolean>>({});
  const operatorProviderModelsRequestedRef = useRef<Set<string>>(new Set());
  const [modelCatalogRows, setModelCatalogRows] = useState<ModelRow[]>([]);
  const [modelCatalogPrefs, setModelCatalogPrefs] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const baseUrl = `${typeof window !== "undefined" ? window.location.origin : ""}/v1`;

  const modelPrefKey = useCallback((providerId: string, modelId: string) => {
    return `${providerId.trim().toLowerCase()}:${modelId.trim()}`;
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setSaveMsg(null);
    try {
      const [
        iRes,
        oRes,
        epRes,
        envLlmRes,
        operatorKindsRes,
        uRes,
        modelsRes,
      ] = await Promise.all([
        apiFetch("/v1/admin/interfaces", auth),
        apiFetch("/v1/admin/operator-settings", auth),
        apiFetch("/v1/admin/external-llm/endpoints", auth),
        apiFetch("/v1/admin/external-llm/env-providers", auth),
        apiFetch("/v1/admin/provider-endpoints", auth),
        apiFetch("/v1/admin/users", auth),
        apiFetch("/v1/admin/model-catalog", auth),
      ]);
      const iData = (await iRes.json()) as InterfaceHints | { detail?: unknown };
      if (!iRes.ok) {
        setSaveMsg({ ok: false, text: detailMessage(iData) });
        return;
      }
      const row = iData as InterfaceHints;
      setDiscordAppId(row.discord_application_id ?? "");
      setTelegramAppId(row.telegram_application_id ?? "");
      const am = row.agent_mode === "sandbox" || row.agent_mode === "host" ? row.agent_mode : "env";
      setAgentMode(am);
      setAgentModeEnv(row.agent_mode_env ?? "sandbox");
      setAgentModeEffective(row.agent_mode_effective ?? row.agent_mode_env ?? "sandbox");

      const oData = (await oRes.json()) as OperatorPublic | { detail?: unknown };
      if (!oRes.ok) {
        setSaveMsg({ ok: false, text: detailMessage(oData) });
        return;
      }
      const op = oData as OperatorPublic;
      setBridgeEnabled(!!op.discord_bot_enabled);
      setTokenConfigured(!!op.discord_bot_token_configured);
      setTriggerPrefix(
        typeof op.discord_trigger_prefix === "string" ? op.discord_trigger_prefix : "!agent "
      );
      setChatModel(op.discord_chat_model ?? "");
      setChatModelProvider(normalizeCatalogRoutingToken(op.discord_chat_model_catalog_owned_by ?? "") ?? "");
      setTgBridgeEnabled(!!op.telegram_bot_enabled);
      setTgTokenConfigured(!!op.telegram_bot_token_configured);
      setTgTriggerPrefix(
        typeof op.telegram_trigger_prefix === "string" ? op.telegram_trigger_prefix : "!agent "
      );
      setTgChatModel(op.telegram_chat_model ?? "");
      setTgChatModelProvider(normalizeCatalogRoutingToken(op.telegram_chat_model_catalog_owned_by ?? "") ?? "");
      const umb = op.dashboard_upload_max_file_mb;
      setUploadMaxMb(umb != null && Number.isFinite(Number(umb)) ? String(umb) : "");
      setUploadMime((op.dashboard_upload_allowed_mime ?? "").trim());
      setUploadEffBytes(
        typeof op.dashboard_upload_effective_max_bytes === "number"
          ? op.dashboard_upload_effective_max_bytes
          : null
      );
      setUploadEffMime(
        Array.isArray(op.dashboard_upload_effective_allowed_mime)
          ? op.dashboard_upload_effective_allowed_mime
          : []
      );
      setMediaLibraryEnabled(!!op.media_library_enabled);
      setMediaUserUploadEnabled(!!op.media_user_upload_enabled);
      setMediaSharingEnabled(!!op.media_sharing_enabled);
      setMediaDefaultQuotaMb(
        op.media_default_user_quota_mb != null && Number.isFinite(Number(op.media_default_user_quota_mb))
          ? String(op.media_default_user_quota_mb)
          : ""
      );
      setMediaUploadMaxMb(
        op.media_upload_max_file_mb != null && Number.isFinite(Number(op.media_upload_max_file_mb))
          ? String(op.media_upload_max_file_mb)
          : ""
      );
      setMediaUploadMime((op.media_upload_allowed_mime ?? "").trim());
      setMediaEmbedHosts((op.media_embed_allowed_hosts ?? "").trim());
      setMediaEffUploadBytes(
        typeof op.media_effective_upload_max_bytes === "number" ? op.media_effective_upload_max_bytes : null
      );
      setMediaEffUploadMime(
        Array.isArray(op.media_effective_upload_allowed_mime) ? op.media_effective_upload_allowed_mime : []
      );
      setMediaEffDefaultQuotaMb(
        typeof op.media_effective_default_quota_mb === "number" ? op.media_effective_default_quota_mb : null
      );
      setVoiceEnabled(!!op.voice_enabled);
      setVoiceApiBaseUrl((op.voice_api_base_url ?? "").trim());
      setVoiceApiBaseSource(
        op.voice_api_base_source === "env" || op.voice_api_base_source === "operator_settings"
          ? op.voice_api_base_source
          : null
      );
      setVoiceApiBaseEffective(
        typeof op.voice_api_base_effective === "string" && op.voice_api_base_effective.trim()
          ? op.voice_api_base_effective.trim()
          : null
      );
      setVoiceApiKey("");
      setVoiceApiKeyConfigured(!!op.voice_api_key_configured);
      setVoiceApiKeySource(
        op.voice_api_key_source === "env" || op.voice_api_key_source === "operator_settings"
          ? op.voice_api_key_source
          : null
      );
      setVoiceSttProviders(Array.isArray(op.voice_stt_providers) ? op.voice_stt_providers : []);
      setVoiceTtsProviders(Array.isArray(op.voice_tts_providers) ? op.voice_tts_providers : []);
      setVoiceSttProviderId((op.voice_stt_provider_id ?? "").trim());
      setVoiceSttProviderIdEffective(
        typeof op.voice_stt_provider_id_effective === "string" && op.voice_stt_provider_id_effective.trim()
          ? op.voice_stt_provider_id_effective.trim()
          : null
      );
      setVoiceTtsProviderId((op.voice_tts_provider_id ?? "").trim());
      setVoiceTtsProviderIdEffective(
        typeof op.voice_tts_provider_id_effective === "string" && op.voice_tts_provider_id_effective.trim()
          ? op.voice_tts_provider_id_effective.trim()
          : null
      );
      setVoiceSttApiBaseEffective(
        typeof op.voice_stt_api_base_effective === "string" && op.voice_stt_api_base_effective.trim()
          ? op.voice_stt_api_base_effective.trim()
          : null
      );
      setVoiceTtsApiBaseEffective(
        typeof op.voice_tts_api_base_effective === "string" && op.voice_tts_api_base_effective.trim()
          ? op.voice_tts_api_base_effective.trim()
          : null
      );
      setVoiceSttModel((op.voice_stt_model ?? "whisper-1").trim() || "whisper-1");
      setVoiceTtsModel((op.voice_tts_model ?? "tts-1").trim() || "tts-1");
      setVoiceTtsVoice((op.voice_tts_voice ?? "alloy").trim() || "alloy");
      setVoiceBridgeTelegram(op.voice_bridge_telegram !== false);
      setVoiceBridgeDiscord(op.voice_bridge_discord !== false);
      setLlmSmartRouting(!!op.llm_smart_routing_enabled);
      setLlmRouterModel((op.llm_router_model ?? "").trim());
      setLlmRouterModelProvider(normalizeCatalogRoutingToken(op.llm_router_model_catalog_owned_by ?? "") ?? "");
      setLlmRouterConfMin(
        op.llm_router_local_confidence_min != null && Number.isFinite(op.llm_router_local_confidence_min)
          ? String(op.llm_router_local_confidence_min)
          : "0.7"
      );
      setLlmRouterTimeoutSec(
        op.llm_router_timeout_sec != null && Number.isFinite(op.llm_router_timeout_sec)
          ? String(op.llm_router_timeout_sec)
          : "12"
      );
      setLlmRouteLongChars(
        op.llm_route_long_prompt_chars != null && Number.isFinite(op.llm_route_long_prompt_chars)
          ? String(op.llm_route_long_prompt_chars)
          : "8000"
      );
      setLlmRouteShortChars(
        op.llm_route_short_local_max_chars != null && Number.isFinite(op.llm_route_short_local_max_chars)
          ? String(op.llm_route_short_local_max_chars)
          : "220"
      );
      setLlmRouteManyFences(
        op.llm_route_many_code_fences != null && Number.isFinite(op.llm_route_many_code_fences)
          ? String(op.llm_route_many_code_fences)
          : "3"
      );
      setLlmRouteManyMsgs(
        op.llm_route_many_messages != null && Number.isFinite(op.llm_route_many_messages)
          ? String(op.llm_route_many_messages)
          : "14"
      );
      const pol = String(op.llm_queue_policy ?? "priority").trim().toLowerCase();
      setLlmQueuePolicy(
        pol === "fifo" || pol === "round_robin" || pol === "priority" ? pol : "priority"
      );
      setLlmQueueUserPriority(
        op.llm_queue_user_priority != null && Number.isFinite(op.llm_queue_user_priority)
          ? String(op.llm_queue_user_priority)
          : "100"
      );
      setLlmQueueBenchmarkPriority(
        op.llm_queue_benchmark_priority != null && Number.isFinite(op.llm_queue_benchmark_priority)
          ? String(op.llm_queue_benchmark_priority)
          : "10"
      );
      setLlmQueueSchedulerPriority(
        op.llm_queue_scheduler_priority != null && Number.isFinite(op.llm_queue_scheduler_priority)
          ? String(op.llm_queue_scheduler_priority)
          : "50"
      );
      setMemoryEnabled(op.memory_enabled !== false);
      setRagEnabled(op.rag_enabled !== false);
      setEmbeddingApiBaseUrl((op.embedding_api_base_url ?? "").trim());
      setEmbeddingApiBaseSource(
        op.embedding_api_base_source === "env" || op.embedding_api_base_source === "operator_settings"
          ? op.embedding_api_base_source
          : null
      );
      setEmbeddingApiBaseEffective(
        typeof op.embedding_api_base_effective === "string" && op.embedding_api_base_effective.trim()
          ? op.embedding_api_base_effective.trim()
          : null
      );
      setEmbeddingApiKey("");
      setEmbeddingApiKeyConfigured(!!op.embedding_api_key_configured);
      setEmbeddingApiKeySource(
        op.embedding_api_key_source === "env" || op.embedding_api_key_source === "operator_settings"
          ? op.embedding_api_key_source
          : null
      );
      setEmbeddingProviders(Array.isArray(op.embedding_providers) ? op.embedding_providers : []);
      setExtractorProviders(Array.isArray(op.extractor_providers) ? op.extractor_providers : []);
      setExtractorApiBaseUrl((op.extractor_api_base_url ?? "").trim());
      setExtractorApiBaseEffective(
        typeof op.extractor_api_base_effective === "string" && op.extractor_api_base_effective.trim()
          ? op.extractor_api_base_effective.trim()
          : null
      );
      setExtractorApiKey("");
      setExtractorApiKeyConfigured(!!op.extractor_api_key_configured);
      const extractorHdrEff =
        typeof op.extractor_api_header_name_effective === "string" &&
        op.extractor_api_header_name_effective.trim()
          ? op.extractor_api_header_name_effective.trim()
          : "X-API-KEY";
      setExtractorApiHeaderNameEffective(extractorHdrEff);
      setExtractorApiHeaderName((op.extractor_api_header_name ?? "").trim() || extractorHdrEff);
      setExtractorProviderId((op.extractor_provider_id ?? "").trim());
      setExtractorProviderIdEffective(
        typeof op.extractor_provider_id_effective === "string" &&
          op.extractor_provider_id_effective.trim()
          ? op.extractor_provider_id_effective.trim()
          : null
      );
      setExtractorModel((op.extractor_model ?? "").trim());
      setExtractorTimeoutSec(
        op.extractor_timeout_sec != null && Number.isFinite(op.extractor_timeout_sec)
          ? String(op.extractor_timeout_sec)
          : "120"
      );
      setRagEmbeddingProviderId((op.rag_embedding_provider_id ?? "").trim());
      setRagEmbeddingProviderIdEffective(
        typeof op.rag_embedding_provider_id_effective === "string" &&
          op.rag_embedding_provider_id_effective.trim()
          ? op.rag_embedding_provider_id_effective.trim()
          : null
      );
      setRagEmbeddingProviderIdSource(
        op.rag_embedding_provider_id_source === "operator_settings"
          ? op.rag_embedding_provider_id_source
          : null
      );
      const hdrEff =
        typeof op.embedding_api_header_name_effective === "string" &&
        op.embedding_api_header_name_effective.trim()
          ? op.embedding_api_header_name_effective.trim()
          : "X-API-KEY";
      setEmbeddingApiHeaderNameEffective(hdrEff);
      setEmbeddingApiHeaderName(
        op.embedding_api_header_name_source === "env"
          ? hdrEff
          : (op.embedding_api_header_name ?? "").trim() || hdrEff
      );
      setEmbeddingApiHeaderNameSource(
        op.embedding_api_header_name_source === "env" ||
          op.embedding_api_header_name_source === "operator_settings"
          ? op.embedding_api_header_name_source
          : null
      );
      setRagEmbeddingModel((op.rag_embedding_model ?? "").trim());
      const applyModelCatalogPayload = (
        modelsJson: AdminModelCatalogPayload & { agentlayer?: { embedding?: EmbeddingCatalogHealth } }
      ) => {
        const emb = modelsJson.agentlayer?.embedding;
        setRagEmbeddingModelOptions(embeddingModelOptions(emb));
        setRagEmbeddingStatusHint(formatEmbeddingStatusHint(emb));
        const rows = Array.isArray(modelsJson.data) ? modelsJson.data : [];
        setModelCatalogRows(rows);
        const prefMap: Record<string, boolean> = {};
        for (const row of rows) {
          const providerId = (row.owned_by ?? "").trim().toLowerCase();
          if (providerId && row.id.trim()) {
            prefMap[modelPrefKey(providerId, row.id)] = true;
          }
        }
        for (const pref of modelsJson.prefs ?? []) {
          const providerId = (pref.provider_id ?? "").trim().toLowerCase();
          const modelId = (pref.model_id ?? "").trim();
          if (providerId && modelId) {
            prefMap[modelPrefKey(providerId, modelId)] = pref.visible_in_chat !== false;
          }
        }
        setModelCatalogPrefs(prefMap);
      };
      try {
        const modelsJson = (await modelsRes.json()) as AdminModelCatalogPayload & {
          agentlayer?: { embedding?: EmbeddingCatalogHealth };
        };
        if (!modelsRes.ok) {
          throw new Error(detailMessage(modelsJson));
        }
        applyModelCatalogPayload(modelsJson);
      } catch {
        const fallback = await fetchModelCatalog(auth);
        applyModelCatalogPayload({ data: fallback.rows, agentlayer: fallback.agentlayer ?? undefined, prefs: [] });
      }
      setRagEmbeddingDim(
        op.rag_embedding_dim != null && Number.isFinite(op.rag_embedding_dim) ? String(op.rag_embedding_dim) : ""
      );
      setRagChunkSize(
        op.rag_chunk_size != null && Number.isFinite(op.rag_chunk_size) ? String(op.rag_chunk_size) : "1200"
      );
      setRagChunkOverlap(
        op.rag_chunk_overlap != null && Number.isFinite(op.rag_chunk_overlap) ? String(op.rag_chunk_overlap) : "200"
      );
      setRagTopK(op.rag_top_k != null && Number.isFinite(op.rag_top_k) ? String(op.rag_top_k) : "8");
      setRagEmbedTimeout(
        op.rag_embed_timeout_sec != null && Number.isFinite(op.rag_embed_timeout_sec)
          ? String(op.rag_embed_timeout_sec)
          : "120"
      );
      setRagTenantDomains((op.rag_tenant_shared_domains ?? "agentlayer_docs").trim());
      setRagTenantEffective(
        Array.isArray(op.rag_tenant_shared_domains_effective) ? op.rag_tenant_shared_domains_effective : []
      );
      setDocsRoot((op.docs_root ?? "").trim());
      setExposeInternalErrors(!!op.expose_internal_errors);
      setHttpClientLogLevel(
        typeof op.http_client_log_level === "string" && op.http_client_log_level.trim()
          ? op.http_client_log_level.trim().toUpperCase()
          : "WARNING"
      );
      setSchedulerEnabled(!!op.scheduler_enabled);
      setSchedulerIntervalMin(
        op.scheduler_interval_minutes != null && Number.isFinite(op.scheduler_interval_minutes)
          ? String(op.scheduler_interval_minutes)
          : "60"
      );
      setSchedulerUserId(typeof op.scheduler_user_id === "string" ? op.scheduler_user_id.trim() : "");
      setSchedulerModel((op.scheduler_model ?? "").trim());
      setSchedulerMaxRounds(
        op.scheduler_max_tool_rounds != null && Number.isFinite(op.scheduler_max_tool_rounds)
          ? String(op.scheduler_max_tool_rounds)
          : ""
      );
      setSchedulerNotifyOnlyIfNotOk(op.scheduler_notify_only_if_not_ok !== false);
      setSchedulerMaxOutbound(
        op.scheduler_max_outbound_per_day != null && Number.isFinite(op.scheduler_max_outbound_per_day)
          ? String(op.scheduler_max_outbound_per_day)
          : "10"
      );
      setSchedulerPackages((op.scheduler_allowed_tool_packages ?? "").trim());
      setSchedulerLlmBackend(
        op.scheduler_llm_backend === "provider" || op.scheduler_llm_backend === "provider_db"
          ? op.scheduler_llm_backend
          : "inherit"
      );
      setSchedulerToolsMode(
        op.scheduler_tools_mode === "allowlist" || op.scheduler_tools_mode === "full"
          ? op.scheduler_tools_mode
          : "none"
      );
      setSchedulerInstructions((op.scheduler_instructions ?? "").trim());
      setSchedulerJobsWorkerEnabled(op.scheduler_jobs_worker_enabled !== false);
      setWorkspaceAllowSelfEditing(!!op.workspace_allow_self_editing);
      setWorkspaceIndexOnWriteDefault(
        op.workspace_index_on_write_default === "off" ||
          op.workspace_index_on_write_default === "immediate"
          ? op.workspace_index_on_write_default
          : "debounced"
      );
      setWorkspaceReindexAfterGitPull(!!op.workspace_reindex_after_git_pull);
      setWorkspaceNightlyReindexEnabled(!!op.workspace_nightly_reindex_enabled);
      setWorkspaceIndexOnAttachEnabled(!!op.workspace_index_on_attach_enabled);

      if (uRes.ok) {
        const uData = (await uRes.json()) as { users?: Array<{ id: string; email?: string | null; display_name?: string | null }> };
        setAdminUsers(Array.isArray(uData.users) ? uData.users : []);
      } else {
        setAdminUsers([]);
      }

      setMemGraphEnabled(op.memory_graph_enabled !== false);
      setMemGraphMaxHops(
        op.memory_graph_max_hops != null && Number.isFinite(Number(op.memory_graph_max_hops))
          ? String(op.memory_graph_max_hops)
          : "2"
      );
      setMemGraphMinScore(
        op.memory_graph_min_score != null && Number.isFinite(Number(op.memory_graph_min_score))
          ? String(op.memory_graph_min_score)
          : "0.03"
      );
      setMemGraphMaxBullets(
        op.memory_graph_max_bullets != null && Number.isFinite(Number(op.memory_graph_max_bullets))
          ? String(op.memory_graph_max_bullets)
          : "14"
      );
      setMemGraphMaxPromptChars(
        op.memory_graph_max_prompt_chars != null && Number.isFinite(Number(op.memory_graph_max_prompt_chars))
          ? String(op.memory_graph_max_prompt_chars)
          : "3500"
      );
      setMemGraphLogActivations(!!op.memory_graph_log_activations);

      if (epRes.ok) {
        const epData = (await epRes.json()) as {
          endpoints?: Array<{
            id: number;
            enabled?: boolean;
            label?: string;
            base_url?: string;
            api_key_configured?: boolean;
            api_header_name?: string | null;
            model_default?: string | null;
            model_vlm?: string | null;
            model_agent?: string | null;
            model_coding?: string | null;
            max_parallel?: number;
          }>;
        };
        const raw = epData.endpoints ?? [];
        setExtLlmEndpoints(
          raw.map((x, i) => ({
            localKey: `ep-${x.id}-${i}`,
            id: x.id,
            enabled: x.enabled !== false,
            label: (x.label ?? "").trim(),
            baseUrl: (x.base_url ?? "").trim(),
            apiKey: "",
            apiKeyConfigured: !!x.api_key_configured,
            apiHeaderName: (x.api_header_name ?? "Authorization").trim() || "Authorization",
            modelDefault: (x.model_default ?? "").trim(),
            modelVlm: (x.model_vlm ?? "").trim(),
            modelAgent: (x.model_agent ?? "").trim(),
            modelCoding: (x.model_coding ?? "").trim(),
            maxParallel:
              typeof x.max_parallel === "number" && Number.isFinite(x.max_parallel)
                ? Math.max(1, Math.min(64, Math.floor(x.max_parallel)))
                : 1,
          }))
        );
      } else {
        setExtLlmEndpoints([]);
      }
      if (envLlmRes.ok) {
        const envData = (await envLlmRes.json()) as EnvLlmProvidersPayload;
        setEnvLlmProviders(Array.isArray(envData.providers) ? envData.providers : []);
        setEnvLlmCleanupNote(typeof envData.cleanup_note === "string" ? envData.cleanup_note : null);
      } else {
        setEnvLlmProviders([]);
        setEnvLlmCleanupNote(null);
      }
      const operatorKindsData = (await operatorKindsRes.json().catch(() => ({}))) as {
        kinds?: OperatorProviderKindMetadata[];
        model_default_profiles?: ModelDefaultProfileMetadata[];
      };
      const operatorProviderMetadata =
        operatorKindsRes.ok && Array.isArray(operatorKindsData.kinds)
          ? operatorKindsData.kinds
              .map((row) => ({
                ...row,
                kind: typeof row.kind === "string" ? row.kind.trim() : "",
                capability: typeof row.capability === "string" ? row.capability.trim() : "",
              }))
              .filter((row) => row.kind && row.capability)
          : [];
      setOperatorProviderKindMetadata(operatorProviderMetadata);
      setModelDefaultProfileMetadata(
        operatorKindsRes.ok && Array.isArray(operatorKindsData.model_default_profiles)
          ? operatorKindsData.model_default_profiles
              .map((row) => ({
                ...row,
                profile: typeof row.profile === "string" ? row.profile.trim() : "",
                capability: typeof row.capability === "string" ? row.capability.trim() : "",
                source: typeof row.source === "string" ? row.source : "",
              }))
              .filter((row) => row.profile && row.capability)
          : []
      );
      const operatorProviderKinds = operatorProviderMetadata.map((row) => row.kind);
      const readOperatorEnv = async (
        res: Response,
      ): Promise<{ providers: OperatorEnvProviderPreview[]; note: string | null }> => {
        if (!res.ok) return { providers: [], note: null };
        const data = (await res.json()) as OperatorEnvProvidersPayload;
        return {
          providers: Array.isArray(data.providers) ? data.providers : [],
          note: typeof data.cleanup_note === "string" ? data.cleanup_note : null,
        };
      };
      const readOperatorEndpoints = async (
        kind: OperatorProviderKind,
        res: Response,
      ): Promise<OperatorProviderEndpointUI[]> => {
        if (!res.ok) return [];
        const data = (await res.json().catch(() => ({}))) as {
          endpoints?: Array<{
            id?: number | null;
            kind?: string;
            provider_id?: string | null;
            source?: string | null;
            enabled?: boolean;
            label?: string | null;
            base_url?: string | null;
            api_key_configured?: boolean;
            api_key_last4?: string | null;
            api_header_name?: string | null;
            model_default?: string | null;
            max_parallel?: number | null;
            options_json?: Record<string, unknown>;
            models?: string[];
            models_detail?: string | null;
          }>;
        };
        return (Array.isArray(data.endpoints) ? data.endpoints : []).map((row) => ({
          id: row.id ?? null,
          kind,
          providerId: (row.provider_id ?? "").trim(),
          source: (row.source ?? "").trim() || "db",
          enabled: row.enabled !== false,
          label: (row.label ?? "").trim(),
          baseUrl: (row.base_url ?? "").trim(),
          apiKey: "",
          apiKeyConfigured: !!row.api_key_configured,
          apiKeyLast4: typeof row.api_key_last4 === "string" ? row.api_key_last4 : null,
          apiHeaderName: (row.api_header_name ?? "Authorization").trim() || "Authorization",
          modelDefault: (row.model_default ?? "").trim(),
          maxParallel: Math.max(1, Math.min(64, Math.floor(Number(row.max_parallel ?? 1) || 1))),
          optionsJson: row.options_json && typeof row.options_json === "object" ? row.options_json : {},
          models: Array.isArray(row.models) ? row.models.map((m) => m.trim()).filter(Boolean) : [],
          modelsDetail: typeof row.models_detail === "string" ? row.models_detail : null,
        }));
      };
      const operatorEnvEntries = await Promise.all(
        operatorProviderKinds.map(async (kind) => {
          const res = await apiFetch(`/v1/admin/provider-endpoints/${kind}/env-providers`, auth);
          return [kind, await readOperatorEnv(res)] as const;
        })
      );
      setEnvOperatorProviders(Object.fromEntries(operatorEnvEntries.map(([kind, data]) => [kind, data.providers])));
      setEnvOperatorCleanupNotes(Object.fromEntries(operatorEnvEntries.map(([kind, data]) => [kind, data.note])));
      const operatorEndpointEntries = await Promise.all(
        operatorProviderKinds.map(async (kind) => {
          const res = await apiFetch(`/v1/admin/provider-endpoints/${kind}`, auth);
          return [kind, await readOperatorEndpoints(kind, res)] as const;
        })
      );
      setOperatorProviderEndpoints(Object.fromEntries(operatorEndpointEntries));
      setOperatorProviderDeleteIds({});
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, [auth, modelPrefKey]);

  const loadExternalModels = useCallback(async () => {
    setExtLlmModelsHint(null);
    setExtLlmModelsLoading(true);
    try {
      const payload: Record<string, string | number> = {};
      const ep0 = extLlmEndpoints.find((e) => e.baseUrl.trim());
      if (ep0?.id != null) {
        payload.endpoint_id = ep0.id;
      } else if (ep0) {
        payload.base_url = ep0.baseUrl.trim();
        const k = ep0.apiKey.trim();
        if (k) payload.api_key = k;
      }
      const res = await apiFetch("/v1/admin/external-llm/models", auth, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const data = (await res.json()) as { data?: Array<{ id?: string }>; detail?: unknown };
      if (!res.ok) {
        setExtLlmModelIds([]);
        setExtLlmModelsHint(detailMessage(data));
        return;
      }
      const ids = (data.data ?? [])
        .map((m) => (typeof m?.id === "string" ? m.id : null))
        .filter((x): x is string => Boolean(x));
      ids.sort((a, b) => a.localeCompare(b));
      setExtLlmModelIds(ids);
      setExtLlmModelsHint(
        ids.length > 0
          ? t("admin:externalModelsLoaded", { count: ids.length })
          : t("admin:externalModelsEmpty")
      );
    } catch (e) {
      setExtLlmModelIds([]);
      setExtLlmModelsHint(e instanceof Error ? e.message : String(e));
    } finally {
      setExtLlmModelsLoading(false);
    }
  }, [auth, extLlmEndpoints, t]);

  const importEnvLlmProviders = useCallback(
    async (providerIndexes?: number[]) => {
      setSaveMsg(null);
      setEnvLlmImporting(true);
      try {
        const body =
          providerIndexes && providerIndexes.length > 0
            ? { provider_indexes: providerIndexes }
            : {};
        const res = await apiFetch("/v1/admin/external-llm/env-providers/import", auth, {
          method: "POST",
          body: JSON.stringify(body),
        });
        const data = (await res.json().catch(() => ({}))) as EnvLlmProvidersPayload & {
          imported?: unknown[];
          updated?: unknown[];
          cleanup_note?: string;
          endpoints?: Array<{
            id: number;
            enabled?: boolean;
            label?: string;
            base_url?: string;
            api_key_configured?: boolean;
            api_header_name?: string | null;
            model_default?: string | null;
            model_vlm?: string | null;
            model_agent?: string | null;
            model_coding?: string | null;
            max_parallel?: number;
          }>;
          env_providers?: EnvLlmProviderPreview[];
        };
        if (!res.ok) {
          setSaveMsg({ ok: false, text: detailMessage(data) });
          return;
        }
        if (Array.isArray(data.endpoints)) {
          setExtLlmEndpoints(
            data.endpoints.map((x, i) => ({
              localKey: `ep-${x.id}-${i}`,
              id: x.id,
              enabled: x.enabled !== false,
              label: (x.label ?? "").trim(),
              baseUrl: (x.base_url ?? "").trim(),
              apiKey: "",
              apiKeyConfigured: !!x.api_key_configured,
              apiHeaderName: (x.api_header_name ?? "Authorization").trim() || "Authorization",
              modelDefault: (x.model_default ?? "").trim(),
              modelVlm: (x.model_vlm ?? "").trim(),
              modelAgent: (x.model_agent ?? "").trim(),
              modelCoding: (x.model_coding ?? "").trim(),
              maxParallel:
                typeof x.max_parallel === "number" && Number.isFinite(x.max_parallel)
                  ? Math.max(1, Math.min(64, Math.floor(x.max_parallel)))
                  : 1,
            }))
          );
        }
        if (Array.isArray(data.env_providers)) {
          setEnvLlmProviders(data.env_providers);
        }
        const imported = Array.isArray(data.imported) ? data.imported.length : 0;
        const updated = Array.isArray(data.updated) ? data.updated.length : 0;
        setSaveMsg({
          ok: true,
          text: t("admin:envLlmImportSuccess", { imported, updated }),
        });
        if (typeof data.cleanup_note === "string") {
          setEnvLlmCleanupNote(data.cleanup_note);
        }
        window.dispatchEvent(new CustomEvent("agentlayer:provider-catalog-changed"));
      } catch (e) {
        setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
      } finally {
        setEnvLlmImporting(false);
      }
    },
    [auth, t]
  );

  const importOperatorEnvProviders = useCallback(
    async (kind: OperatorProviderKind, providerIndexes?: number[]) => {
      setSaveMsg(null);
      setEnvOperatorImporting(kind);
      try {
        const body =
          providerIndexes && providerIndexes.length > 0
            ? { provider_indexes: providerIndexes }
            : {};
        const res = await apiFetch(`/v1/admin/provider-endpoints/${kind}/env-providers/import`, auth, {
          method: "POST",
          body: JSON.stringify(body),
        });
        const data = (await res.json().catch(() => ({}))) as OperatorEnvProvidersPayload & {
          imported?: unknown[];
          updated?: unknown[];
          cleanup_note?: string;
          endpoints?: Array<{
            id?: number | null;
            kind?: string;
            provider_id?: string | null;
            source?: string | null;
            enabled?: boolean;
            label?: string | null;
            base_url?: string | null;
            api_key_configured?: boolean;
            api_key_last4?: string | null;
            api_header_name?: string | null;
            model_default?: string | null;
            max_parallel?: number | null;
            options_json?: Record<string, unknown>;
            models?: string[];
            models_detail?: string | null;
          }>;
          env_providers?: OperatorEnvProviderPreview[];
        };
        if (!res.ok) {
          setSaveMsg({ ok: false, text: detailMessage(data) });
          return;
        }
        if (Array.isArray(data.env_providers)) {
          setEnvOperatorProviders((prev) => ({ ...prev, [kind]: data.env_providers ?? [] }));
        }
        if (Array.isArray(data.endpoints)) {
          setOperatorProviderEndpoints((prev) => ({
            ...prev,
            [kind]: data.endpoints!.map((row) => ({
              id: row.id ?? null,
              kind,
              providerId: (row.provider_id ?? "").trim(),
              source: (row.source ?? "").trim() || "db",
              enabled: row.enabled !== false,
              label: (row.label ?? "").trim(),
              baseUrl: (row.base_url ?? "").trim(),
              apiKey: "",
              apiKeyConfigured: !!row.api_key_configured,
              apiKeyLast4: typeof row.api_key_last4 === "string" ? row.api_key_last4 : null,
              apiHeaderName: (row.api_header_name ?? "Authorization").trim() || "Authorization",
              modelDefault: (row.model_default ?? "").trim(),
              maxParallel: Math.max(1, Math.min(64, Math.floor(Number(row.max_parallel ?? 1) || 1))),
              optionsJson: row.options_json && typeof row.options_json === "object" ? row.options_json : {},
              models: Array.isArray(row.models) ? row.models.map((m) => m.trim()).filter(Boolean) : [],
              modelsDetail: typeof row.models_detail === "string" ? row.models_detail : null,
            })),
          }));
          setOperatorProviderDeleteIds((prev) => ({ ...prev, [kind]: [] }));
        }
        if (typeof data.cleanup_note === "string") {
          setEnvOperatorCleanupNotes((prev) => ({ ...prev, [kind]: data.cleanup_note ?? null }));
        }
        const opRes = await apiFetch("/v1/admin/operator-settings", auth);
        const op = (await opRes.json().catch(() => ({}))) as OperatorPublic;
        if (opRes.ok) {
          setEmbeddingProviders(Array.isArray(op.embedding_providers) ? op.embedding_providers : []);
          setExtractorProviders(Array.isArray(op.extractor_providers) ? op.extractor_providers : []);
          setVoiceSttProviders(Array.isArray(op.voice_stt_providers) ? op.voice_stt_providers : []);
          setVoiceTtsProviders(Array.isArray(op.voice_tts_providers) ? op.voice_tts_providers : []);
        }
        window.dispatchEvent(new CustomEvent("agentlayer:provider-catalog-changed"));
        const imported = Array.isArray(data.imported) ? data.imported.length : 0;
        const updated = Array.isArray(data.updated) ? data.updated.length : 0;
        setSaveMsg({
          ok: true,
          text: t("admin:envProviderImportSuccess", { imported, updated }),
        });
      } catch (e) {
        setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
      } finally {
        setEnvOperatorImporting(null);
      }
    },
    [auth, t]
  );

  const operatorProviderModelKey = useCallback((kind: OperatorProviderKind, providerId: string) => {
    return `${kind}:${providerId.trim()}`;
  }, []);

  const loadOperatorProviderModels = useCallback(
    async (kind: OperatorProviderKind, providerId: string) => {
      const provider = providerId.trim();
      if (!provider) return;
      const key = operatorProviderModelKey(kind, provider);
      if (operatorProviderModelsRequestedRef.current.has(key)) return;
      operatorProviderModelsRequestedRef.current.add(key);
      setOperatorProviderModelsLoading((prev) => ({ ...prev, [key]: true }));
      try {
        const qs = new URLSearchParams({ provider_id: provider });
        const res = await apiFetch(`/v1/admin/provider-endpoints/${kind}/models?${qs}`, auth);
        const data = (await res.json().catch(() => ({}))) as { data?: Array<{ id?: unknown }> };
        if (!res.ok) {
          setOperatorProviderModelOptions((prev) => ({ ...prev, [key]: [] }));
          return;
        }
        const ids = (data.data ?? [])
          .map((row) => (typeof row.id === "string" ? row.id.trim() : ""))
          .filter(Boolean)
          .sort((a, b) => a.localeCompare(b));
        setOperatorProviderModelOptions((prev) => ({ ...prev, [key]: [...new Set(ids)] }));
      } finally {
        setOperatorProviderModelsLoading((prev) => ({ ...prev, [key]: false }));
      }
    },
    [auth, operatorProviderModelKey]
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaveMsg(null);
    try {
      const putRes = await apiFetch("/v1/admin/interfaces", auth, {
        method: "PUT",
        body: JSON.stringify({
          discord_application_id: discordAppId.trim(),
          telegram_application_id: telegramAppId.trim(),
          agent_mode: agentMode === "env" ? "" : agentMode,
        }),
      });
      const putData = await putRes.json();
      if (!putRes.ok) {
        setSaveMsg({ ok: false, text: detailMessage(putData) });
        return;
      }
      const row = putData as InterfaceHints;
      setDiscordAppId(row.discord_application_id ?? "");
      setTelegramAppId(row.telegram_application_id ?? "");
      const am = row.agent_mode === "sandbox" || row.agent_mode === "host" ? row.agent_mode : "env";
      setAgentMode(am);
      setAgentModeEnv(row.agent_mode_env ?? "sandbox");
      setAgentModeEffective(row.agent_mode_effective ?? row.agent_mode_env ?? "sandbox");

      const patch: Record<string, unknown> = {
        discord_bot_enabled: bridgeEnabled,
        discord_trigger_prefix: triggerPrefix.trim(),
        discord_chat_model: chatModel.trim() || null,
        discord_chat_model_catalog_owned_by: chatModelProvider.trim() || null,
        telegram_bot_enabled: tgBridgeEnabled,
        telegram_trigger_prefix: tgTriggerPrefix.trim(),
        telegram_chat_model: tgChatModel.trim() || null,
        telegram_chat_model_catalog_owned_by: tgChatModelProvider.trim() || null,
      };
      const mbStr = uploadMaxMb.trim();
      if (mbStr === "") {
        patch.dashboard_upload_max_file_mb = null;
      } else {
        const n = Number(mbStr);
        if (!Number.isFinite(n) || n < 1) {
          setSaveMsg({
            ok: false,
            text: t("admin:operatorSaveDashboardUploadInvalid"),
          });
          return;
        }
        patch.dashboard_upload_max_file_mb = Math.min(512, Math.floor(n));
      }
      const mimeStr = uploadMime.trim();
      patch.dashboard_upload_allowed_mime = mimeStr === "" ? null : mimeStr;
      const confMin = Number(llmRouterConfMin.trim());
      const rtSec = Number(llmRouterTimeoutSec.trim());
      const longC = Number(llmRouteLongChars.trim());
      const shortC = Number(llmRouteShortChars.trim());
      const manyF = Number(llmRouteManyFences.trim());
      const manyM = Number(llmRouteManyMsgs.trim());
      if (
        !Number.isFinite(confMin) ||
        confMin < 0 ||
        confMin > 1 ||
        !Number.isFinite(rtSec) ||
        rtSec < 1 ||
        rtSec > 120 ||
        !Number.isFinite(longC) ||
        longC < 100 ||
        longC > 500000 ||
        !Number.isFinite(shortC) ||
        shortC < 1 ||
        shortC > 50000 ||
        !Number.isFinite(manyF) ||
        manyF < 1 ||
        manyF > 100 ||
        !Number.isFinite(manyM) ||
        manyM < 1 ||
        manyM > 500
      ) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveSmartRoutingInvalid"),
        });
        return;
      }
      patch.llm_smart_routing_enabled = llmSmartRouting;
      patch.llm_router_model = llmRouterModel.trim() || null;
      patch.llm_router_model_catalog_owned_by = llmRouterModelProvider.trim() || null;
      patch.llm_router_local_confidence_min = confMin;
      patch.llm_router_timeout_sec = rtSec;
      patch.llm_route_long_prompt_chars = Math.floor(longC);
      patch.llm_route_short_local_max_chars = Math.floor(shortC);
      patch.llm_route_many_code_fences = Math.floor(manyF);
      patch.llm_route_many_messages = Math.floor(manyM);
      const uPrio = Number(llmQueueUserPriority.trim());
      const bPrio = Number(llmQueueBenchmarkPriority.trim());
      const sPrio = Number(llmQueueSchedulerPriority.trim());
      if (
        !Number.isFinite(uPrio) ||
        uPrio < 0 ||
        uPrio > 1000 ||
        !Number.isFinite(bPrio) ||
        bPrio < 0 ||
        bPrio > 1000 ||
        !Number.isFinite(sPrio) ||
        sPrio < 0 ||
        sPrio > 1000
      ) {
        setSaveMsg({ ok: false, text: t("admin:operatorSaveLlmQueueInvalid") });
        return;
      }
      patch.llm_queue_policy = llmQueuePolicy;
      patch.llm_queue_user_priority = Math.floor(uPrio);
      patch.llm_queue_benchmark_priority = Math.floor(bPrio);
      patch.llm_queue_scheduler_priority = Math.floor(sPrio);
      const red = Number(ragEmbeddingDim.trim());
      const rcs = Number(ragChunkSize.trim());
      const rco = Number(ragChunkOverlap.trim());
      const rtk = Number(ragTopK.trim());
      const ret = Number(ragEmbedTimeout.trim());
      if (
        !Number.isFinite(red) ||
        red < 32 ||
        red > 4096 ||
        !Number.isFinite(rcs) ||
        rcs < 200 ||
        rcs > 8000 ||
        !Number.isFinite(rco) ||
        rco < 0 ||
        rco > 2000 ||
        !Number.isFinite(rtk) ||
        rtk < 1 ||
        rtk > 50 ||
        !Number.isFinite(ret) ||
        ret < 5 ||
        ret > 600
      ) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveRagInvalid"),
        });
        return;
      }
      patch.memory_enabled = memoryEnabled;
      patch.rag_enabled = ragEnabled;
      const embBase = embeddingApiBaseUrl.trim();
      patch.embedding_api_base_url = embBase ? embBase : null;
      patch.embedding_api_header_name = embeddingApiHeaderName.trim() || null;
      if (embeddingApiKey.trim()) {
        patch.embedding_api_key = embeddingApiKey.trim();
      }
      patch.rag_embedding_provider_id = ragEmbeddingProviderId.trim() || null;
      const extractorTimeout = Number(extractorTimeoutSec.trim());
      if (
        !Number.isFinite(extractorTimeout) ||
        extractorTimeout < 1 ||
        extractorTimeout > 1800
      ) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveExtractorInvalid"),
        });
        return;
      }
      patch.extractor_api_base_url = extractorApiBaseUrl.trim() || null;
      patch.extractor_api_header_name = extractorApiHeaderName.trim() || null;
      if (extractorApiKey.trim()) {
        patch.extractor_api_key = extractorApiKey.trim();
      }
      patch.extractor_provider_id = extractorProviderId.trim() || null;
      patch.extractor_model = extractorModel.trim() || null;
      patch.extractor_timeout_sec = extractorTimeout;
      patch.rag_embedding_model = ragEmbeddingModel.trim();
      patch.rag_embedding_dim = Math.floor(red);
      patch.rag_chunk_size = Math.floor(rcs);
      patch.rag_chunk_overlap = Math.floor(rco);
      patch.rag_top_k = Math.floor(rtk);
      patch.rag_embed_timeout_sec = ret;
      patch.rag_tenant_shared_domains = ragTenantDomains.trim();
      patch.docs_root = docsRoot.trim() ? docsRoot.trim() : null;
      patch.expose_internal_errors = exposeInternalErrors;
      patch.http_client_log_level = httpClientLogLevel.trim() || "WARNING";
      patch.scheduler_enabled = schedulerEnabled;
      const hInt = Number(schedulerIntervalMin.trim());
      patch.scheduler_interval_minutes =
        Number.isFinite(hInt) && hInt >= 5 && hInt <= 1440 ? Math.floor(hInt) : 60;
      patch.scheduler_user_id = schedulerUserId.trim() ? schedulerUserId.trim() : null;
      patch.scheduler_model = schedulerModel.trim() ? schedulerModel.trim() : null;
      const hMr = Number(schedulerMaxRounds.trim());
      patch.scheduler_max_tool_rounds =
        schedulerMaxRounds.trim() && Number.isFinite(hMr) && hMr >= 1 && hMr <= 64
          ? Math.floor(hMr)
          : null;
      patch.scheduler_notify_only_if_not_ok = schedulerNotifyOnlyIfNotOk;
      const hOut = Number(schedulerMaxOutbound.trim());
      patch.scheduler_max_outbound_per_day =
        Number.isFinite(hOut) && hOut >= 0 && hOut <= 100000 ? Math.floor(hOut) : 10;
      patch.scheduler_allowed_tool_packages = schedulerPackages.trim() || null;
      patch.scheduler_llm_backend = schedulerLlmBackend;
      patch.scheduler_tools_mode = schedulerToolsMode;
      patch.scheduler_pidea_enabled = false;
      patch.scheduler_instructions = schedulerInstructions.trim() || null;
      patch.scheduler_jobs_worker_enabled = schedulerJobsWorkerEnabled;
      patch.scheduler_jobs_ide_pidea_enabled = false;
      patch.scheduler_jobs_ide_pidea_timeout_sec = 300;
      patch.workspace_allow_self_editing = workspaceAllowSelfEditing;
      patch.workspace_index_on_write_default = workspaceIndexOnWriteDefault;
      patch.workspace_reindex_after_git_pull = workspaceReindexAfterGitPull;
      patch.workspace_nightly_reindex_enabled = workspaceNightlyReindexEnabled;
      patch.workspace_index_on_attach_enabled = workspaceIndexOnAttachEnabled;
      patch.media_library_enabled = mediaLibraryEnabled;
      patch.media_user_upload_enabled = mediaUserUploadEnabled;
      patch.media_sharing_enabled = mediaSharingEnabled;
      const mdq = mediaDefaultQuotaMb.trim();
      if (mdq === "") {
        patch.media_default_user_quota_mb = null;
      } else {
        const n = Number(mdq);
        if (!Number.isFinite(n) || n < 1) {
          setSaveMsg({ ok: false, text: t("admin:operatorSaveMediaQuotaInvalid") });
          return;
        }
        patch.media_default_user_quota_mb = Math.min(50_000, Math.floor(n));
      }
      const mum = mediaUploadMaxMb.trim();
      if (mum === "") {
        patch.media_upload_max_file_mb = null;
      } else {
        const n = Number(mum);
        if (!Number.isFinite(n) || n < 1) {
          setSaveMsg({ ok: false, text: t("admin:operatorSaveMediaUploadInvalid") });
          return;
        }
        patch.media_upload_max_file_mb = Math.min(512, Math.floor(n));
      }
      patch.media_upload_allowed_mime = mediaUploadMime.trim() === "" ? null : mediaUploadMime.trim();
      patch.media_embed_allowed_hosts = mediaEmbedHosts.trim() === "" ? null : mediaEmbedHosts.trim();
      patch.voice_enabled = voiceEnabled;
      patch.voice_stt_provider_id = voiceSttProviderId.trim() || null;
      patch.voice_tts_provider_id = voiceTtsProviderId.trim() || null;
      if (voiceApiBaseSource !== "env") {
        patch.voice_api_base_url = voiceApiBaseUrl.trim() || null;
      }
      if (voiceApiKey.trim()) patch.voice_api_key = voiceApiKey.trim();
      patch.voice_stt_model = voiceSttModel.trim() || "whisper-1";
      patch.voice_tts_model = voiceTtsModel.trim() || "tts-1";
      patch.voice_tts_voice = voiceTtsVoice.trim() || "alloy";
      patch.voice_bridge_telegram = voiceBridgeTelegram;
      patch.voice_bridge_discord = voiceBridgeDiscord;
      patch.voice_realtime_enabled = voiceRealtimeEnabled;
      patch.voice_discord_vc_enabled = voiceDiscordVcEnabled;
      const mgHops = Number(memGraphMaxHops.trim());
      const mgScore = Number(memGraphMinScore.trim());
      const mgBullets = Number(memGraphMaxBullets.trim());
      const mgChars = Number(memGraphMaxPromptChars.trim());
      if (
        !Number.isFinite(mgHops) ||
        mgHops < 0 ||
        mgHops > 4 ||
        !Number.isFinite(mgScore) ||
        mgScore < 0 ||
        mgScore > 1 ||
        !Number.isFinite(mgBullets) ||
        mgBullets < 1 ||
        mgBullets > 50 ||
        !Number.isFinite(mgChars) ||
        mgChars < 200 ||
        mgChars > 50000
      ) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveMemGraphInvalid"),
        });
        return;
      }
      patch.memory_graph_enabled = memGraphEnabled;
      patch.memory_graph_max_hops = Math.floor(mgHops);
      patch.memory_graph_min_score = mgScore;
      patch.memory_graph_max_bullets = Math.floor(mgBullets);
      patch.memory_graph_max_prompt_chars = Math.floor(mgChars);
      patch.memory_graph_log_activations = memGraphLogActivations;
      if (discordToken.trim()) {
        patch.discord_bot_token = discordToken.trim();
      }
      if (telegramToken.trim()) {
        patch.telegram_bot_token = telegramToken.trim();
      }
      const patchRes = await apiFetch("/v1/admin/operator-settings", auth, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      const patchData = await patchRes.json();
      if (!patchRes.ok) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveInterfacesPartial", { detail: detailMessage(patchData) }),
        });
        return;
      }
      const hasGenericChatProvider = operatorProviderKindMetadata.some((metadata) => metadata.kind === "chat");
      if (!hasGenericChatProvider) {
        for (let i = 0; i < extLlmEndpoints.length; i++) {
          const r = extLlmEndpoints[i];
          if (!r.baseUrl.trim()) {
            setSaveMsg({
              ok: false,
              text: t("admin:operatorSaveLlmMissingUrl", { n: i + 1 }),
            });
            return;
          }
        }
        const epPayload = {
          endpoints: extLlmEndpoints.map((r, idx) => {
            const o: Record<string, unknown> = {
              sort_order: idx,
              enabled: r.enabled !== false,
              label: r.label.trim(),
              base_url: r.baseUrl.trim(),
              api_header_name: r.apiHeaderName.trim() || "Authorization",
              max_parallel: Math.max(1, Math.min(64, Math.floor(r.maxParallel || 1))),
            };
            if (r.id != null) o.id = r.id;
            const k = r.apiKey.trim();
            if (k) o.api_key = k;
            return o;
          }),
        };
        const epRes = await apiFetch("/v1/admin/external-llm/endpoints", auth, {
          method: "PUT",
          body: JSON.stringify(epPayload),
        });
        const epData = await epRes.json();
        if (!epRes.ok) {
          setSaveMsg({
            ok: false,
            text: t("admin:operatorSaveLlmEndpointsPartial", { detail: detailMessage(epData) }),
          });
          return;
        }
      }
      for (const metadata of operatorProviderKindMetadata) {
        if (!Object.prototype.hasOwnProperty.call(operatorProviderEndpoints, metadata.kind)) {
          continue;
        }
        const rows = operatorProviderEndpoints[metadata.kind] ?? [];
        const endpoints = rows.filter((row) => row.id != null || row.baseUrl.trim() || row.label.trim() || (row.apiKey ?? "").trim());
        for (let i = 0; i < endpoints.length; i++) {
          if (!endpoints[i].baseUrl.trim()) {
            setSaveMsg({
              ok: false,
              text: t("admin:operatorSaveLlmMissingUrl", { n: i + 1 }),
            });
            return;
          }
        }
        const providerEndpointRes = await apiFetch(`/v1/admin/provider-endpoints/${metadata.kind}`, auth, {
          method: "PUT",
          body: JSON.stringify({
            delete_endpoint_ids: operatorProviderDeleteIds[metadata.kind] ?? [],
            endpoints: endpoints.map((row, idx) => {
              const out: Record<string, unknown> = {
                sort_order: idx,
                enabled: row.enabled !== false,
                label: row.label.trim(),
                base_url: row.baseUrl.trim(),
                api_header_name: row.apiHeaderName.trim() || "Authorization",
                model_default: row.modelDefault.trim() || null,
                max_parallel: Math.max(1, Math.min(64, Math.floor(row.maxParallel || 1))),
                options_json: row.optionsJson ?? {},
              };
              if (row.id != null) out.id = row.id;
              const apiKey = (row.apiKey ?? "").trim();
              if (apiKey) out.api_key = apiKey;
              return out;
            }),
          }),
        });
        const providerEndpointData = await providerEndpointRes.json();
        if (!providerEndpointRes.ok) {
          setSaveMsg({
            ok: false,
            text: t("admin:operatorSaveLlmEndpointsPartial", { detail: detailMessage(providerEndpointData) }),
          });
          return;
        }
        setOperatorProviderDeleteIds((prev) => ({ ...prev, [metadata.kind]: [] }));
      }
      const prefPayload = modelCatalogRows
        .map((row, idx): ModelCatalogPref | null => {
          const providerId = (row.owned_by ?? "").trim().toLowerCase();
          const modelId = row.id.trim();
          if (!providerId || !modelId) return null;
          return {
            provider_id: providerId,
            model_id: modelId,
            visible_in_chat: modelCatalogPrefs[modelPrefKey(providerId, modelId)] !== false,
            profile_tags: [],
            sort_order: idx,
          };
        })
        .filter((x): x is ModelCatalogPref => x !== null);
      const prefRes = await apiFetch("/v1/admin/model-catalog/prefs", auth, {
        method: "PUT",
        body: JSON.stringify({ prefs: prefPayload }),
      });
      const prefData = await prefRes.json();
      if (!prefRes.ok) {
        setSaveMsg({
          ok: false,
          text: t("admin:operatorSaveModelCatalogPrefsPartial", {
            detail: detailMessage(prefData),
          }),
        });
        return;
      }
      setDiscordToken("");
      setTelegramToken("");
      await load();
      setSaveMsg({
        ok: true,
        text: t("admin:operatorSaveOkBridges"),
      });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  const refreshEmbeddingCatalog = useCallback(async () => {
    setEmbeddingModelsLoading(true);
    try {
      const modelsRes = await apiFetch("/v1/models", auth);
      const modelsJson = (await modelsRes.json()) as { agentlayer?: { embedding?: EmbeddingCatalogHealth } };
      const emb = modelsJson.agentlayer?.embedding;
      setRagEmbeddingModelOptions(embeddingModelOptions(emb));
      setRagEmbeddingStatusHint(formatEmbeddingStatusHint(emb));
    } catch {
      setRagEmbeddingModelOptions([]);
      setRagEmbeddingStatusHint(t("admin:embeddingModelListLoadFailed"));
    } finally {
      setEmbeddingModelsLoading(false);
    }
  }, [auth, t]);

  async function clearTelegramToken() {
    setSaveMsg(null);
    try {
      const res = await apiFetch("/v1/admin/operator-settings", auth, {
        method: "PATCH",
        body: JSON.stringify({ telegram_bot_token: null }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveMsg({ ok: false, text: detailMessage(data) });
        return;
      }
      await load();
      setSaveMsg({ ok: true, text: t("admin:telegramTokenCleared") });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  async function clearDiscordToken() {
    setSaveMsg(null);
    try {
      const res = await apiFetch("/v1/admin/operator-settings", auth, {
        method: "PATCH",
        body: JSON.stringify({ discord_bot_token: null }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveMsg({ ok: false, text: detailMessage(data) });
        return;
      }
      await load();
      setSaveMsg({ ok: true, text: t("admin:discordTokenCleared") });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  return {
    auth,
    baseUrl,
    loading,
    saveMsg,
    setSaveMsg,
    discordAppId,
    setDiscordAppId,
    telegramAppId,
    setTelegramAppId,
    agentMode,
    setAgentMode,
    agentModeEnv,
    agentModeEffective,
    bridgeEnabled,
    setBridgeEnabled,
    tokenConfigured,
    triggerPrefix,
    setTriggerPrefix,
    chatModel,
    setChatModel,
    chatModelProvider,
    setChatModelProvider,
    discordToken,
    setDiscordToken,
    tgBridgeEnabled,
    setTgBridgeEnabled,
    tgTokenConfigured,
    tgTriggerPrefix,
    setTgTriggerPrefix,
    tgChatModel,
    setTgChatModel,
    tgChatModelProvider,
    setTgChatModelProvider,
    telegramToken,
    setTelegramToken,
    uploadMaxMb,
    setUploadMaxMb,
    uploadMime,
    setUploadMime,
    uploadEffBytes,
    uploadEffMime,
    mediaLibraryEnabled,
    setMediaLibraryEnabled,
    mediaUserUploadEnabled,
    setMediaUserUploadEnabled,
    mediaSharingEnabled,
    setMediaSharingEnabled,
    mediaDefaultQuotaMb,
    setMediaDefaultQuotaMb,
    mediaUploadMaxMb,
    setMediaUploadMaxMb,
    mediaUploadMime,
    setMediaUploadMime,
    mediaEmbedHosts,
    setMediaEmbedHosts,
    mediaEffUploadBytes,
    mediaEffUploadMime,
    mediaEffDefaultQuotaMb,
    voiceEnabled,
    setVoiceEnabled,
    voiceApiBaseUrl,
    setVoiceApiBaseUrl,
    voiceApiBaseSource,
    voiceApiBaseEffective,
    voiceApiKey,
    setVoiceApiKey,
    voiceApiKeyConfigured,
    voiceApiKeySource,
    voiceSttProviderId,
    setVoiceSttProviderId,
    voiceSttProviderIdEffective,
    voiceTtsProviderId,
    setVoiceTtsProviderId,
    voiceTtsProviderIdEffective,
    voiceSttApiBaseEffective,
    voiceTtsApiBaseEffective,
    voiceSttProviders,
    voiceTtsProviders,
    voiceSttModel,
    setVoiceSttModel,
    voiceTtsModel,
    setVoiceTtsModel,
    voiceTtsVoice,
    setVoiceTtsVoice,
    voiceBridgeTelegram,
    setVoiceBridgeTelegram,
    voiceBridgeDiscord,
    setVoiceBridgeDiscord,
    voiceRealtimeEnabled,
    setVoiceRealtimeEnabled,
    voiceDiscordVcEnabled,
    setVoiceDiscordVcEnabled,
    extLlmEndpoints,
    setExtLlmEndpoints,
    envLlmProviders,
    envLlmCleanupNote,
    envLlmImporting,
    importEnvLlmProviders,
    envOperatorProviders,
    operatorProviderEndpoints,
    operatorProviderDeleteIds,
    setOperatorProviderEndpoints,
    setOperatorProviderDeleteIds,
    envOperatorCleanupNotes,
    operatorProviderKindMetadata,
    modelDefaultProfileMetadata,
    envOperatorImporting,
    importOperatorEnvProviders,
    operatorProviderModelOptions,
    operatorProviderModelsLoading,
    operatorProviderModelKey,
    loadOperatorProviderModels,
    llmSmartRouting,
    setLlmSmartRouting,
    llmRouterModel,
    setLlmRouterModel,
    llmRouterModelProvider,
    setLlmRouterModelProvider,
    llmRouterConfMin,
    setLlmRouterConfMin,
    llmRouterTimeoutSec,
    setLlmRouterTimeoutSec,
    llmRouteLongChars,
    setLlmRouteLongChars,
    llmRouteShortChars,
    setLlmRouteShortChars,
    llmRouteManyFences,
    setLlmRouteManyFences,
    llmRouteManyMsgs,
    setLlmRouteManyMsgs,
    llmQueuePolicy,
    setLlmQueuePolicy,
    llmQueueUserPriority,
    setLlmQueueUserPriority,
    llmQueueBenchmarkPriority,
    setLlmQueueBenchmarkPriority,
    llmQueueSchedulerPriority,
    setLlmQueueSchedulerPriority,
    memGraphEnabled,
    setMemGraphEnabled,
    memGraphMaxHops,
    setMemGraphMaxHops,
    memGraphMinScore,
    setMemGraphMinScore,
    memGraphMaxBullets,
    setMemGraphMaxBullets,
    memGraphMaxPromptChars,
    setMemGraphMaxPromptChars,
    memGraphLogActivations,
    setMemGraphLogActivations,
    memoryEnabled,
    setMemoryEnabled,
    ragEnabled,
    setRagEnabled,
    embeddingApiBaseUrl,
    setEmbeddingApiBaseUrl,
    embeddingApiBaseSource,
    embeddingApiBaseEffective,
    embeddingApiKey,
    setEmbeddingApiKey,
    embeddingApiKeyConfigured,
    embeddingApiKeySource,
    embeddingApiHeaderName,
    setEmbeddingApiHeaderName,
    embeddingApiHeaderNameEffective,
    embeddingApiHeaderNameSource,
    ragEmbeddingModel,
    setRagEmbeddingModel,
    ragEmbeddingModelOptions,
    ragEmbeddingStatusHint,
    embeddingModelsLoading,
    refreshEmbeddingCatalog,
    ragEmbeddingProviderId,
    setRagEmbeddingProviderId,
    ragEmbeddingProviderIdEffective,
    ragEmbeddingProviderIdSource,
    embeddingProviders,
    extractorProviders,
    extractorApiBaseUrl,
    setExtractorApiBaseUrl,
    extractorApiBaseEffective,
    extractorApiKey,
    setExtractorApiKey,
    extractorApiKeyConfigured,
    extractorApiHeaderName,
    setExtractorApiHeaderName,
    extractorApiHeaderNameEffective,
    extractorProviderId,
    setExtractorProviderId,
    extractorProviderIdEffective,
    extractorModel,
    setExtractorModel,
    extractorTimeoutSec,
    setExtractorTimeoutSec,
    ragEmbeddingDim,
    setRagEmbeddingDim,
    ragChunkSize,
    setRagChunkSize,
    ragChunkOverlap,
    setRagChunkOverlap,
    ragTopK,
    setRagTopK,
    ragEmbedTimeout,
    setRagEmbedTimeout,
    ragTenantDomains,
    setRagTenantDomains,
    ragTenantEffective,
    docsRoot,
    setDocsRoot,
    exposeInternalErrors,
    setExposeInternalErrors,
    httpClientLogLevel,
    setHttpClientLogLevel,
    schedulerEnabled,
    setSchedulerEnabled,
    schedulerIntervalMin,
    setSchedulerIntervalMin,
    schedulerUserId,
    setSchedulerUserId,
    schedulerModel,
    setSchedulerModel,
    schedulerMaxRounds,
    setSchedulerMaxRounds,
    schedulerNotifyOnlyIfNotOk,
    setSchedulerNotifyOnlyIfNotOk,
    schedulerMaxOutbound,
    setSchedulerMaxOutbound,
    schedulerPackages,
    setSchedulerPackages,
    schedulerLlmBackend,
    setSchedulerLlmBackend,
    schedulerToolsMode,
    setSchedulerToolsMode,
    schedulerInstructions,
    setSchedulerInstructions,
    schedulerJobsWorkerEnabled,
    setSchedulerJobsWorkerEnabled,
    workspaceAllowSelfEditing,
    setWorkspaceAllowSelfEditing,
    workspaceIndexOnWriteDefault,
    setWorkspaceIndexOnWriteDefault,
    workspaceReindexAfterGitPull,
    setWorkspaceReindexAfterGitPull,
    workspaceNightlyReindexEnabled,
    setWorkspaceNightlyReindexEnabled,
    workspaceIndexOnAttachEnabled,
    setWorkspaceIndexOnAttachEnabled,
    adminUsers,
    extLlmModelIds,
    extLlmModelsLoading,
    extLlmModelsHint,
    modelCatalogRows,
    setModelCatalogRows,
    modelCatalogPrefs,
    setModelCatalogPrefs,
    modelPrefKey,
    load,
    save,
    loadExternalModels,
    clearTelegramToken,
    clearDiscordToken,
  };
}

export type OperatorSettingsContextValue = ReturnType<typeof useOperatorSettingsState>;

const OperatorSettingsContext = createContext<OperatorSettingsContextValue | null>(null);

export function OperatorSettingsProvider({ children }: { children: ReactNode }) {
  const value = useOperatorSettingsState();
  return (
    <OperatorSettingsContext.Provider value={value}>{children}</OperatorSettingsContext.Provider>
  );
}

export function useOperatorSettings(): OperatorSettingsContextValue {
  const ctx = useContext(OperatorSettingsContext);
  if (!ctx) {
    throw new Error("useOperatorSettings must be used within OperatorSettingsProvider");
  }
  return ctx;
}
