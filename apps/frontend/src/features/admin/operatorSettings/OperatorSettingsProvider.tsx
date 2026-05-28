import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";
import {
  embeddingModelOptions,
  formatEmbeddingStatusHint,
  type EmbeddingCatalogHealth,
} from "../../../lib/modelCatalog";
import {
  detailMessage,
  type ExternalLlmEndpointUI,
  type InterfaceHints,
  type OperatorPublic,
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
  const [discordToken, setDiscordToken] = useState("");
  const [tgBridgeEnabled, setTgBridgeEnabled] = useState(false);
  const [tgTokenConfigured, setTgTokenConfigured] = useState(false);
  const [tgTriggerPrefix, setTgTriggerPrefix] = useState("!agent ");
  const [tgChatModel, setTgChatModel] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [uploadMaxMb, setUploadMaxMb] = useState("");
  const [uploadMime, setUploadMime] = useState("");
  const [uploadEffBytes, setUploadEffBytes] = useState<number | null>(null);
  const [uploadEffMime, setUploadEffMime] = useState<string[]>([]);
  const [extLlmEndpoints, setExtLlmEndpoints] = useState<ExternalLlmEndpointUI[]>([]);
  const [llmSmartRouting, setLlmSmartRouting] = useState(false);
  const [llmRouterModel, setLlmRouterModel] = useState("nemotron-3-nano:4b");
  const [llmRouterConfMin, setLlmRouterConfMin] = useState("0.7");
  const [llmRouterTimeoutSec, setLlmRouterTimeoutSec] = useState("12");
  const [llmRouteLongChars, setLlmRouteLongChars] = useState("8000");
  const [llmRouteShortChars, setLlmRouteShortChars] = useState("220");
  const [llmRouteManyFences, setLlmRouteManyFences] = useState("3");
  const [llmRouteManyMsgs, setLlmRouteManyMsgs] = useState("14");
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
  const [ragEmbeddingDim, setRagEmbeddingDim] = useState("768");
  const [ragChunkSize, setRagChunkSize] = useState("1200");
  const [ragChunkOverlap, setRagChunkOverlap] = useState("200");
  const [ragTopK, setRagTopK] = useState("8");
  const [ragEmbedTimeout, setRagEmbedTimeout] = useState("120");
  const [ragTenantDomains, setRagTenantDomains] = useState("agentlayer_docs");
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
  const [adminUsers, setAdminUsers] = useState<Array<{ id: string; email?: string | null; display_name?: string | null }>>([]);
  const [extLlmModelIds, setExtLlmModelIds] = useState<string[]>([]);
  const [extLlmModelsLoading, setExtLlmModelsLoading] = useState(false);
  const [extLlmModelsHint, setExtLlmModelsHint] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const baseUrl = `${typeof window !== "undefined" ? window.location.origin : ""}/v1`;

  const load = useCallback(async () => {
    setLoading(true);
    setSaveMsg(null);
    try {
      const [iRes, oRes, epRes, uRes, modelsRes] = await Promise.all([
        apiFetch("/v1/admin/interfaces", auth),
        apiFetch("/v1/admin/operator-settings", auth),
        apiFetch("/v1/admin/external-llm/endpoints", auth),
        apiFetch("/v1/admin/users", auth),
        fetch("/v1/models"),
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
      setTgBridgeEnabled(!!op.telegram_bot_enabled);
      setTgTokenConfigured(!!op.telegram_bot_token_configured);
      setTgTriggerPrefix(
        typeof op.telegram_trigger_prefix === "string" ? op.telegram_trigger_prefix : "!agent "
      );
      setTgChatModel(op.telegram_chat_model ?? "");
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
      setLlmSmartRouting(!!op.llm_smart_routing_enabled);
      setLlmRouterModel((op.llm_router_ollama_model ?? "nemotron-3-nano:4b").trim() || "nemotron-3-nano:4b");
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
      setRagEmbeddingModel(
        (op.rag_embedding_model ?? (op as { rag_ollama_model?: string }).rag_ollama_model ?? "").trim()
      );
      try {
        const modelsJson = (await modelsRes.json()) as { agentlayer?: { embedding?: EmbeddingCatalogHealth } };
        const emb = modelsJson.agentlayer?.embedding;
        setRagEmbeddingModelOptions(embeddingModelOptions(emb));
        setRagEmbeddingStatusHint(formatEmbeddingStatusHint(emb));
      } catch {
        setRagEmbeddingModelOptions([]);
        setRagEmbeddingStatusHint(null);
      }
      setRagEmbeddingDim(
        op.rag_embedding_dim != null && Number.isFinite(op.rag_embedding_dim) ? String(op.rag_embedding_dim) : "768"
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
        op.scheduler_llm_backend === "ollama" || op.scheduler_llm_backend === "external"
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
            model_default?: string | null;
            model_vlm?: string | null;
            model_agent?: string | null;
            model_coding?: string | null;
          }>;
        };
        const raw = epData.endpoints ?? [];
        setExtLlmEndpoints(
          raw.map((x, i) => ({
            localKey: `ep-${x.id}-${i}`,
            id: x.id,
            enabled: true,
            label: (x.label ?? "").trim(),
            baseUrl: (x.base_url ?? "").trim(),
            apiKey: "",
            apiKeyConfigured: !!x.api_key_configured,
            modelDefault: (x.model_default ?? "").trim(),
            modelVlm: (x.model_vlm ?? "").trim(),
            modelAgent: (x.model_agent ?? "").trim(),
            modelCoding: (x.model_coding ?? "").trim(),
          }))
        );
      } else {
        setExtLlmEndpoints([]);
      }
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, [auth]);

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
        telegram_bot_enabled: tgBridgeEnabled,
        telegram_trigger_prefix: tgTriggerPrefix.trim(),
        telegram_chat_model: tgChatModel.trim() || null,
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
      patch.llm_router_ollama_model = llmRouterModel.trim() || "nemotron-3-nano:4b";
      patch.llm_router_local_confidence_min = confMin;
      patch.llm_router_timeout_sec = rtSec;
      patch.llm_route_long_prompt_chars = Math.floor(longC);
      patch.llm_route_short_local_max_chars = Math.floor(shortC);
      patch.llm_route_many_code_fences = Math.floor(manyF);
      patch.llm_route_many_messages = Math.floor(manyM);
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
      for (let i = 0; i < extLlmEndpoints.length; i++) {
        const r = extLlmEndpoints[i];
        if (!r.baseUrl.trim()) {
          setSaveMsg({
            ok: false,
            text: t("admin:operatorSaveLlmMissingUrl", { n: i + 1 }),
          });
          return;
        }
        if (r.id == null && !r.apiKey.trim()) {
          setSaveMsg({
            ok: false,
            text: t("admin:operatorSaveLlmMissingKey", { n: i + 1 }),
          });
          return;
        }
      }
      const epPayload = {
        endpoints: extLlmEndpoints.map((r, idx) => {
          const o: Record<string, unknown> = {
            sort_order: idx,
            enabled: true,
            label: r.label.trim(),
            base_url: r.baseUrl.trim(),
            model_default: r.modelDefault.trim() || null,
            model_vlm: r.modelVlm.trim() || null,
            model_agent: r.modelAgent.trim() || null,
            model_coding: r.modelCoding.trim() || null,
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
      const modelsRes = await fetch("/v1/models");
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
  }, [t]);

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
    discordToken,
    setDiscordToken,
    tgBridgeEnabled,
    setTgBridgeEnabled,
    tgTokenConfigured,
    tgTriggerPrefix,
    setTgTriggerPrefix,
    tgChatModel,
    setTgChatModel,
    telegramToken,
    setTelegramToken,
    uploadMaxMb,
    setUploadMaxMb,
    uploadMime,
    setUploadMime,
    uploadEffBytes,
    uploadEffMime,
    extLlmEndpoints,
    setExtLlmEndpoints,
    llmSmartRouting,
    setLlmSmartRouting,
    llmRouterModel,
    setLlmRouterModel,
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
    adminUsers,
    extLlmModelIds,
    extLlmModelsLoading,
    extLlmModelsHint,
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
