import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import {
  embeddingModelOptions,
  type EmbeddingCatalogHealth,
} from "../../lib/modelCatalog";

type InterfaceHints = {
  discord_application_id: string;
  telegram_application_id?: string;
  agent_mode?: "" | "sandbox" | "host";
  agent_mode_effective?: "sandbox" | "host";
  agent_mode_env?: "sandbox" | "host";
};

type OperatorPublic = {
  discord_bot_enabled?: boolean;
  discord_bot_token_configured?: boolean;
  discord_trigger_prefix?: string;
  discord_chat_model?: string;
  telegram_bot_enabled?: boolean;
  telegram_bot_token_configured?: boolean;
  telegram_trigger_prefix?: string;
  telegram_chat_model?: string;
  dashboard_upload_max_file_mb?: number | null;
  dashboard_upload_allowed_mime?: string;
  dashboard_upload_effective_max_bytes?: number;
  dashboard_upload_effective_allowed_mime?: string[];
  llm_primary_backend?: "ollama" | "external";
  llm_smart_routing_enabled?: boolean;
  llm_router_ollama_model?: string;
  llm_router_local_confidence_min?: number;
  llm_router_timeout_sec?: number;
  llm_route_long_prompt_chars?: number;
  llm_route_short_local_max_chars?: number;
  llm_route_many_code_fences?: number;
  llm_route_many_messages?: number;
  memory_graph_enabled?: boolean;
  memory_graph_max_hops?: number;
  memory_graph_min_score?: number;
  memory_graph_max_bullets?: number;
  memory_graph_max_prompt_chars?: number;
  memory_graph_log_activations?: boolean;
  memory_enabled?: boolean;
  rag_enabled?: boolean;
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
  /** httpx/httpcore: WARNING = quiet long-poll; INFO = per-request */
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
  detail?: unknown;
};

type ExternalLlmEndpointUI = {
  localKey: string;
  id: number | null;
  enabled: boolean;
  label: string;
  baseUrl: string;
  apiKey: string;
  apiKeyConfigured: boolean;
  modelDefault: string;
  modelVlm: string;
  modelAgent: string;
  modelCoding: string;
};

function detailMessage(data: unknown): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return JSON.stringify(d);
  }
  return "Request failed";
}

function externalLlmEndpointHostPreview(baseUrl: string): string {
  const u = baseUrl.trim();
  if (!u) return "";
  try {
    return new URL(u).host;
  } catch {
    return u.length > 48 ? `${u.slice(0, 45)}…` : u;
  }
}

export function AdminInterfaces() {
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
  const [llmPrimaryBackend, setLlmPrimaryBackend] = useState<"ollama" | "external">("ollama");
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
  const [ragEmbeddingModel, setRagEmbeddingModel] = useState("nomic-embed-text");
  const [ragEmbeddingModelOptions, setRagEmbeddingModelOptions] = useState<string[]>([]);
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
      setLlmPrimaryBackend(op.llm_primary_backend === "external" ? "external" : "ollama");
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
      setRagEmbeddingModel(
        (op.rag_embedding_model ?? (op as { rag_ollama_model?: string }).rag_ollama_model ?? "nomic-embed-text")
          .trim() || "nomic-embed-text"
      );
      try {
        const modelsJson = (await modelsRes.json()) as { agentlayer?: { embedding?: EmbeddingCatalogHealth } };
        setRagEmbeddingModelOptions(embeddingModelOptions(modelsJson.agentlayer?.embedding));
      } catch {
        setRagEmbeddingModelOptions([]);
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
          ? `${ids.length} Modellnamen geladen — Vorschläge erscheinen beim Tippen in den Feldern unten.`
          : "Die API hat keine Modelle geliefert (leere Liste)."
      );
    } catch (e) {
      setExtLlmModelIds([]);
      setExtLlmModelsHint(e instanceof Error ? e.message : String(e));
    } finally {
      setExtLlmModelsLoading(false);
    }
  }, [auth, extLlmEndpoints]);

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
            text: "Dashboard upload: max file MB must be empty (use env) or an integer ≥ 1.",
          });
          return;
        }
        patch.dashboard_upload_max_file_mb = Math.min(512, Math.floor(n));
      }
      const mimeStr = uploadMime.trim();
      patch.dashboard_upload_allowed_mime = mimeStr === "" ? null : mimeStr;
      patch.llm_primary_backend = llmPrimaryBackend;
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
          text: "Smart routing: Ungültige Zahlen (siehe Hilfetext zu den Grenzen).",
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
          text: "RAG: Ungültige Zahlen (Dim 32–4096, Chunk 200–8000, Overlap 0–2000, Top-K 1–50, Timeout 5–600).",
        });
        return;
      }
      patch.memory_enabled = memoryEnabled;
      patch.rag_enabled = ragEnabled;
      patch.rag_embedding_model = ragEmbeddingModel.trim() || "nomic-embed-text";
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
          text: "Memory graph: Ungültige Zahlen (Hops 0–4, Score 0–1, Bullets 1–50, Zeichen 200–50000).",
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
          text: `Interfaces saved, but operator settings failed: ${detailMessage(patchData)}`,
        });
        return;
      }
      for (let i = 0; i < extLlmEndpoints.length; i++) {
        const r = extLlmEndpoints[i];
        if (!r.baseUrl.trim()) {
          setSaveMsg({
            ok: false,
            text: `Externe LLM: Endpoint ${i + 1}: Base URL fehlt (oder Zeile entfernen).`,
          });
          return;
        }
        if (r.id == null && !r.apiKey.trim()) {
          setSaveMsg({
            ok: false,
            text: `Externe LLM: Neuer Endpoint ${i + 1}: API-Key erforderlich.`,
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
          text: `Einstellungen gespeichert, aber externe LLM-Endpoints: ${detailMessage(epData)}`,
        });
        return;
      }
      setDiscordToken("");
      setTelegramToken("");
      await load();
      setSaveMsg({
        ok: true,
        text: "Saved. In-process Discord/Telegram bridges pick up token/enable changes after the current session reconnects (or restart the container).",
      });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

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
      setSaveMsg({ ok: true, text: "Telegram bot token cleared." });
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
      setSaveMsg({ ok: true, text: "Discord bot token cleared." });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="mx-auto max-w-xl px-6 py-10">
      <h1 className="text-2xl font-semibold text-white">Interfaces</h1>
      <p className="mt-2 text-sm text-surface-muted">
        Point OpenAI-compatible clients at <span className="font-mono text-neutral-300">{baseUrl}</span>
        ; use a JWT or user API key as Bearer. Full rules:{" "}
        <a href="/auth/policy" className="text-sky-400 hover:underline">
          GET /auth/policy
        </a>
        . Discord and Telegram gateways and application ids live here too (not on a separate admin page).
      </p>

      {loading ? (
        <p className="mt-6 text-sm text-surface-muted">Loading…</p>
      ) : (
        <>
          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Agent mode</h2>
            <p className="mt-2 text-xs text-surface-muted">
              <span className="font-mono text-neutral-400">AGENT_MODE</span> in <span className="font-mono">.env</span>{" "}
              is the default (<span className="text-neutral-300">sandbox</span> = Docker-bound: tools
              always run as <span className="font-mono">container</span> for policy;
              <span className="text-neutral-300"> host</span> = allow host-class overrides per tool
              policy). Here you can override that for the running deployment (saved in the database).
              Choose &quot;Use environment&quot; to clear the override.
            </p>
            <p className="mt-2 text-xs text-surface-muted">
              Env: <span className="font-mono text-neutral-300">{agentModeEnv}</span>
              {" · "}
              Effective: <span className="font-mono text-neutral-300">{agentModeEffective}</span>
            </p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="agent-mode">
              Operator override
            </label>
            <select
              id="agent-mode"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={agentMode}
              onChange={(e) => setAgentMode(e.target.value as "env" | "sandbox" | "host")}
            >
              <option value="env">Use environment (AGENT_MODE)</option>
              <option value="sandbox">sandbox (force Docker-bound tool execution)</option>
              <option value="host">host (allow host-class tool policy)</option>
            </select>
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Dashboard uploads</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Globale Grenzen für Galerie-Uploads (JPEG/PNG/GIF/WebP). Leer = Umgebungsvariablen{" "}
              <span className="font-mono text-neutral-400">AGENT_DASHBOARD_UPLOAD_MAX_MB</span> /{" "}
              <span className="font-mono text-neutral-400">AGENT_DASHBOARD_UPLOAD_ALLOWED_MIME</span>
              .
            </p>
            {uploadEffBytes != null ? (
              <p className="mt-2 text-xs text-surface-muted">
                Aktuell wirksam: max{" "}
                <span className="font-mono text-neutral-300">{uploadEffBytes}</span> Bytes · MIME:{" "}
                <span className="font-mono text-neutral-300">{uploadEffMime.join(", ") || "—"}</span>
              </p>
            ) : null}
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mb">
              Max. Dateigröße (MB), leer = nur Env/Standard
            </label>
            <input
              id="wu-mb"
              type="number"
              min={1}
              max={512}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={uploadMaxMb}
              onChange={(e) => setUploadMaxMb(e.target.value)}
              placeholder="z. B. 10"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mime">
              Erlaubte MIME-Typen (kommagetrennt), leer = nur Env/Standard
            </label>
            <input
              id="wu-mime"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={uploadMime}
              onChange={(e) => setUploadMime(e.target.value)}
              placeholder="image/jpeg,image/png,image/gif,image/webp"
            />
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Memory (Fakten &amp; Notizen) &amp; RAG</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Alles in <span className="font-mono text-neutral-400">operator_settings</span> — keine{" "}
              <span className="font-mono text-neutral-400">AGENT_MEMORY_*</span> /{" "}
              <span className="font-mono text-neutral-400">AGENT_RAG_*</span> mehr. Tool-Pakete weiter unter{" "}
              <span className="text-white/85">Admin → Tools</span>.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={exposeInternalErrors}
                onChange={(e) => setExposeInternalErrors(e.target.checked)}
              />
              Interne Fehlertexte in API-Antworten (5xx/502) — nur zum Debuggen; in Produktion aus lassen
            </label>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={memoryEnabled}
                onChange={(e) => setMemoryEnabled(e.target.checked)}
              />
              Memory (Fakten, semantische Notizen, APIs) aktivieren
            </label>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={ragEnabled}
                onChange={(e) => setRagEnabled(e.target.checked)}
              />
              RAG (pgvector-Ingest &amp; Suche) aktivieren
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="rag-model">
              Embedding-Modell (RAG, von EMBEDDING_BASE_URL /v1/models)
            </label>
            {ragEmbeddingModelOptions.length > 0 ? (
              <select
                id="rag-model"
                className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                value={ragEmbeddingModel}
                onChange={(e) => setRagEmbeddingModel(e.target.value)}
              >
                {ragEmbeddingModelOptions.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="rag-model"
                className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                value={ragEmbeddingModel}
                onChange={(e) => setRagEmbeddingModel(e.target.value)}
                placeholder="nomic-embed-text"
                autoComplete="off"
              />
            )}
            <p className="mt-1 text-xs text-surface-muted">
              API-Host nur in <span className="font-mono">.env</span> (EMBEDDING_BASE_URL). Liste kommt von GET /v1/models
              am Embedding-Server. Beim Speichern übernimmt der Server die passende{" "}
              <span className="font-mono">Embedding-Dim</span> automatisch vom gewählten Modell (z. B. bge-m3 → 1024).
            </p>
            <div className="mt-4 grid max-w-2xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-dim">
                  Embedding-Dim (32–4096)
                </label>
                <input
                  id="rag-dim"
                  type="number"
                  min={32}
                  max={4096}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={ragEmbeddingDim}
                  onChange={(e) => setRagEmbeddingDim(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-chunk">
                  Chunk-Größe (200–8000)
                </label>
                <input
                  id="rag-chunk"
                  type="number"
                  min={200}
                  max={8000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={ragChunkSize}
                  onChange={(e) => setRagChunkSize(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-overlap">
                  Chunk-Overlap (0–2000)
                </label>
                <input
                  id="rag-overlap"
                  type="number"
                  min={0}
                  max={2000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={ragChunkOverlap}
                  onChange={(e) => setRagChunkOverlap(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-topk">
                  Top-K (1–50)
                </label>
                <input
                  id="rag-topk"
                  type="number"
                  min={1}
                  max={50}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={ragTopK}
                  onChange={(e) => setRagTopK(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-timeout">
                  Embed-Timeout (Sek., 5–600)
                </label>
                <input
                  id="rag-timeout"
                  type="number"
                  min={5}
                  max={600}
                  step="1"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={ragEmbedTimeout}
                  onChange={(e) => setRagEmbedTimeout(e.target.value)}
                />
              </div>
            </div>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="rag-domains">
              Tenant-weite Domains (kommagetrennt). Leer = keine tenant-weiten Domains; Standard oft{" "}
              <span className="font-mono text-neutral-300">agentlayer_docs</span>.
            </label>
            <input
              id="rag-domains"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={ragTenantDomains}
              onChange={(e) => setRagTenantDomains(e.target.value)}
              placeholder="agentlayer_docs"
            />
            {ragTenantEffective.length > 0 ? (
              <p className="mt-2 text-xs text-surface-muted">
                Wirksam geparst:{" "}
                <span className="font-mono text-neutral-300">{ragTenantEffective.join(", ")}</span>
              </p>
            ) : null}
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="docs-root">
              Docs-Pfad für <span className="font-mono text-neutral-400">ingest-docs</span> (optional, leer ={" "}
              <span className="font-mono text-neutral-300">…/docs</span> im Image)
            </label>
            <input
              id="docs-root"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={docsRoot}
              onChange={(e) => setDocsRoot(e.target.value)}
              placeholder="/pfad/zum/docs"
              autoComplete="off"
            />
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Memory graph</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Strukturierte Knoten/Kanten + Prompt-Injection. Gespeichert in der Datenbank (
              <span className="font-mono text-neutral-400">operator_settings</span>
              ). Benötigt aktiviertes Memory oben. Tool-Paket weiter unter{" "}
              <span className="text-white/85">Admin → Tools</span>.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={memGraphEnabled}
                onChange={(e) => setMemGraphEnabled(e.target.checked)}
              />
              Graph-Speicherung und Kontext-Injection aktivieren
            </label>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={memGraphLogActivations}
                onChange={(e) => setMemGraphLogActivations(e.target.checked)}
              />
              Aktivierungs-Log schreiben (node ids, gehashte Query — kein Rohtext)
            </label>
            <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="mg-hops">
                  Max. Hops (0–4)
                </label>
                <input
                  id="mg-hops"
                  type="number"
                  min={0}
                  max={4}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={memGraphMaxHops}
                  onChange={(e) => setMemGraphMaxHops(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="mg-score">
                  Min. Aktivierungsscore (0–1)
                </label>
                <input
                  id="mg-score"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={memGraphMinScore}
                  onChange={(e) => setMemGraphMinScore(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="mg-bullets">
                  Max. Bullet-Zeilen
                </label>
                <input
                  id="mg-bullets"
                  type="number"
                  min={1}
                  max={50}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={memGraphMaxBullets}
                  onChange={(e) => setMemGraphMaxBullets(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="mg-chars">
                  Max. Zeichen (Graph-Block)
                </label>
                <input
                  id="mg-chars"
                  type="number"
                  min={200}
                  max={50000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={memGraphMaxPromptChars}
                  onChange={(e) => setMemGraphMaxPromptChars(e.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Agent-Chat: Backend</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Nur diese eine Auswahl: wo Agent-Chat-Completions laufen.{" "}
              <span className="text-white/85">Kein API-Key in diesem Block</span> — URL, Key und Modell-IDs trägst du in
              der Karte <span className="text-white/85">Externe LLM-Endpoints</span> direkt unter diesem Block ein.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="llm-backend">
              Backend
            </label>
            <select
              id="llm-backend"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={llmPrimaryBackend}
              onChange={(e) => setLlmPrimaryBackend(e.target.value as "ollama" | "external")}
            >
              <option value="ollama">Ollama (OLLAMA_BASE_URL)</option>
              <option value="external">Extern (OpenAI-kompatible API)</option>
            </select>
            <p className="mt-3 text-xs text-surface-muted">
              <span className="text-white/80">Ollama</span> = alles über den lokalen Dienst.{" "}
              <span className="text-white/80">Extern</span> = Completions über die in der{" "}
              <span className="text-white/80">nächsten</span> Karte hinterlegte URL + Key (Profil-Modell-IDs dort).
            </p>
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Smart LLM-Routing</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Pro Anfrage zwischen lokalem Ollama und externer API wählen (Heuristik + kleines Router-Modell auf
              Ollama). Nur sinnvoll, wenn du <span className="text-white/85">beide</span> Backends nutzen willst
              (externe Zugangsdaten in der nächsten Karte). Gespeichert in der Datenbank — keine Umgebungsvariablen.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={llmSmartRouting}
                onChange={(e) => setLlmSmartRouting(e.target.checked)}
              />
              Smart Routing aktivieren
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="llm-router-model">
              Router-Modell (Ollama, klein, z. B. 3–6B)
            </label>
            <input
              id="llm-router-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={llmRouterModel}
              onChange={(e) => setLlmRouterModel(e.target.value)}
              placeholder="nemotron-3-nano:4b"
              autoComplete="off"
            />
            <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-router-conf">
                  Min. Konfidenz für „lokal“ (0–1)
                </label>
                <input
                  id="llm-router-conf"
                  type="number"
                  step="0.05"
                  min={0}
                  max={1}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouterConfMin}
                  onChange={(e) => setLlmRouterConfMin(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-router-to">
                  Router-Timeout (Sekunden, 1–120)
                </label>
                <input
                  id="llm-router-to"
                  type="number"
                  min={1}
                  max={120}
                  step="1"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouterTimeoutSec}
                  onChange={(e) => setLlmRouterTimeoutSec(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-long">
                  Lange letzte User-Nachricht ab (Zeichen) → eher extern
                </label>
                <input
                  id="llm-route-long"
                  type="number"
                  min={100}
                  max={500000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouteLongChars}
                  onChange={(e) => setLlmRouteLongChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-short">
                  Kurze Nachricht bis (Zeichen) → eher lokal
                </label>
                <input
                  id="llm-route-short"
                  type="number"
                  min={1}
                  max={50000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouteShortChars}
                  onChange={(e) => setLlmRouteShortChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-fences">
                  Code-Blöcke (Schwelle, ≥)
                </label>
                <input
                  id="llm-route-fences"
                  type="number"
                  min={1}
                  max={100}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouteManyFences}
                  onChange={(e) => setLlmRouteManyFences(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-msgs">
                  Viele Turns (über) → eher extern
                </label>
                <input
                  id="llm-route-msgs"
                  type="number"
                  min={1}
                  max={500}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={llmRouteManyMsgs}
                  onChange={(e) => setLlmRouteManyMsgs(e.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">LLM-Endpoints (Chat-Provider)</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Jeder Eintrag = ein Provider im Model-Dropdown (<span className="font-mono">external_1</span>,{" "}
              <span className="font-mono">external_2</span>, …). Kein Aktivieren nötig — URL + Key eintragen, speichern,
              dann im Chat Modell wählen. Reihenfolge = Failover nur für Legacy{" "}
              <span className="font-mono">external</span>. OpenAI-kompatibel: OpenAI, Groq, Gemini, eigene llama.cpp-URL, …
              Zusätzlich: <span className="font-mono">OLLAMA_BASE_URL</span> und{" "}
              <span className="font-mono">LLAMA_CPP_*</span> in <span className="font-mono">.env</span> erscheinen als{" "}
              <span className="font-mono">ollama</span> / <span className="font-mono">llama_cpp</span>.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20"
                onClick={() =>
                  setExtLlmEndpoints((prev) => [
                    ...prev,
                    {
                      localKey: `new-${Date.now()}`,
                      id: null,
                      enabled: true,
                      label: "",
                      baseUrl: "",
                      apiKey: "",
                      apiKeyConfigured: false,
                      modelDefault: "",
                      modelVlm: "",
                      modelAgent: "",
                      modelCoding: "",
                    },
                  ])
                }
              >
                Endpoint hinzufügen
              </button>
              <button
                type="button"
                className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
                disabled={extLlmModelsLoading}
                onClick={() => void loadExternalModels()}
              >
                {extLlmModelsLoading ? "Lade Modelle…" : "Modelle laden (erster Endpoint mit URL)"}
              </button>
            </div>
            {extLlmModelsHint ? (
              <p
                className={`mt-2 text-xs ${
                  extLlmModelIds.length > 0 ? "text-emerald-400/90" : "text-amber-300/90"
                }`}
              >
                {extLlmModelsHint}
              </p>
            ) : null}
            <datalist id="ext-llm-model-ids">
              {extLlmModelIds.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>

            <div className="mt-6 space-y-6">
              {extLlmEndpoints.map((ep, idx) => (
                <div
                  key={ep.localKey}
                  className="rounded-lg border border-white/10 bg-black/15 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium text-surface-muted">
                      Endpoint {idx + 1}
                      {ep.id != null ? (
                        <span className="ml-2 font-mono text-neutral-500">id={ep.id}</span>
                      ) : null}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="text-xs text-neutral-400 hover:text-white"
                        disabled={idx === 0}
                        onClick={() =>
                          setExtLlmEndpoints((prev) => {
                            const n = [...prev];
                            [n[idx - 1], n[idx]] = [n[idx], n[idx - 1]];
                            return n;
                          })
                        }
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="text-xs text-neutral-400 hover:text-white"
                        disabled={idx >= extLlmEndpoints.length - 1}
                        onClick={() =>
                          setExtLlmEndpoints((prev) => {
                            const n = [...prev];
                            [n[idx], n[idx + 1]] = [n[idx + 1], n[idx]];
                            return n;
                          })
                        }
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="text-xs text-rose-400 hover:text-rose-200"
                        onClick={() =>
                          setExtLlmEndpoints((prev) => prev.filter((_, j) => j !== idx))
                        }
                      >
                        Entfernen
                      </button>
                    </div>
                  </div>
                  <label className="mt-2 block text-xs text-surface-muted" htmlFor={`ep-lbl-${ep.localKey}`}>
                    Label (optional)
                  </label>
                  <input
                    id={`ep-lbl-${ep.localKey}`}
                    className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
                    value={ep.label}
                    onChange={(e) => {
                      const v = e.target.value;
                      setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, label: v } : x))
                      );
                    }}
                    placeholder="z. B. Google, OpenAI Backup"
                  />
                  <label className="mt-3 block text-xs text-surface-muted" htmlFor={`ep-url-${ep.localKey}`}>
                    Base URL
                  </label>
                  <input
                    id={`ep-url-${ep.localKey}`}
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                    value={ep.baseUrl}
                    onChange={(e) => {
                      const v = e.target.value;
                      setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, baseUrl: v } : x))
                      );
                    }}
                    placeholder="https://api.openai.com"
                    autoComplete="off"
                  />
                  <p className="mt-1 text-xs text-surface-muted">
                    Key: {ep.apiKeyConfigured ? "gespeichert" : "—"}
                  </p>
                  <label className="mt-2 block text-xs text-surface-muted" htmlFor={`ep-key-${ep.localKey}`}>
                    API-Key (leer lassen = gespeicherten Key behalten)
                  </label>
                  <input
                    id={`ep-key-${ep.localKey}`}
                    type="password"
                    autoComplete="off"
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                    value={ep.apiKey}
                    onChange={(e) => {
                      const v = e.target.value;
                      setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, apiKey: v } : x))
                      );
                    }}
                    placeholder={ep.apiKeyConfigured ? "•••• (neu = ersetzen)" : "Key einfügen"}
                  />
                  <h4 className="mt-4 text-xs font-medium uppercase tracking-wide text-surface-muted">
                    Modell-IDs (OpenAI-Namen)
                  </h4>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-md-${ep.localKey}`}>
                        Default
                      </label>
                      <input
                        id={`ep-md-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelDefault}
                        onChange={(e) => {
                          const v = e.target.value;
                          setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelDefault: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-mv-${ep.localKey}`}>
                        VLM
                      </label>
                      <input
                        id={`ep-mv-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelVlm}
                        onChange={(e) => {
                          const v = e.target.value;
                          setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelVlm: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-ma-${ep.localKey}`}>
                        Agent
                      </label>
                      <input
                        id={`ep-ma-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelAgent}
                        onChange={(e) => {
                          const v = e.target.value;
                          setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelAgent: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-mc-${ep.localKey}`}>
                        Coding
                      </label>
                      <input
                        id={`ep-mc-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelCoding}
                        onChange={(e) => {
                          const v = e.target.value;
                          setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelCoding: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {extLlmEndpoints.length === 0 ? (
              <p className="mt-4 text-xs text-amber-300/90">
                Keine externen Endpoints — es wird bei Bedarf die alte Einzel-Konfiguration in{" "}
                <span className="font-mono">operator_settings</span> genutzt (Migration legt ggf. eine Zeile an).
                Endpoint hinzufügen für Multi-Provider / Failover.
              </p>
            ) : null}
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Discord</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Application id is a hint for integrations. The in-process bridge runs inside agent-layer; users link their
              numeric Discord user id under <strong className="text-neutral-300">Settings → Connections</strong>. With a
              trigger prefix, only messages that start with it are handled; leave the prefix field empty so the bot
              reacts to <strong className="text-neutral-300">every</strong> text message in the channel (only linked
              users; noisy in busy servers). Chat runs in-process as the linked AgentLayer user.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="discord-id">
              Discord application ID
            </label>
            <input
              id="discord-id"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={discordAppId}
              onChange={(e) => setDiscordAppId(e.target.value)}
              autoComplete="off"
              inputMode="numeric"
            />

            <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">In-process bridge</h3>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={bridgeEnabled}
                onChange={(e) => setBridgeEnabled(e.target.checked)}
              />
              Enable Discord bridge
            </label>
            <p className="mt-2 text-xs text-surface-muted">Token stored: {tokenConfigured ? "yes" : "no"}</p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="d-token">
              Discord bot token (Developer Portal)
            </label>
            <input
              id="d-token"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={discordToken}
              onChange={(e) => setDiscordToken(e.target.value)}
              placeholder={tokenConfigured ? "•••••• (enter new value to replace)" : "paste token"}
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="prefix">
              Message prefix (must match start of message); <strong className="text-neutral-300">empty</strong> = no
              prefix (every message is a prompt)
            </label>
            <input
              id="prefix"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={triggerPrefix}
              onChange={(e) => setTriggerPrefix(e.target.value)}
              placeholder="e.g. !agent  — leave empty for no prefix"
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="model">
              Ollama model id (empty = server default)
            </label>
            <input
              id="model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={chatModel}
              onChange={(e) => setChatModel(e.target.value)}
              placeholder="e.g. nemotron-3-nano:4b"
            />
            <button
              type="button"
              className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              disabled={!tokenConfigured}
              onClick={() => void clearDiscordToken()}
            >
              Clear Discord token
            </button>
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Telegram</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Bot username / hint for integrations. The in-process bridge runs inside agent-layer; users link their
              numeric Telegram user id under <strong className="text-neutral-300">Settings → Connections</strong>. With a
              trigger prefix, only messages that start with it are handled; leave the prefix field empty so the bot
              reacts to <strong className="text-neutral-300">every</strong> text message (only linked users; in groups
              set @BotFather <span className="font-mono">/setprivacy</span> to <strong className="text-neutral-300">Disable</strong>{" "}
              so the bot sees normal messages). Chat runs in-process as the linked AgentLayer user.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="telegram-app-hint">
              Telegram bot username or note (optional)
            </label>
            <input
              id="telegram-app-hint"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={telegramAppId}
              onChange={(e) => setTelegramAppId(e.target.value)}
              autoComplete="off"
              placeholder="@YourBotName"
            />

            <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">In-process bridge</h3>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={tgBridgeEnabled}
                onChange={(e) => setTgBridgeEnabled(e.target.checked)}
              />
              Enable Telegram bridge
            </label>
            <p className="mt-2 text-xs text-surface-muted">Token stored: {tgTokenConfigured ? "yes" : "no"}</p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-token">
              Telegram bot token (@BotFather)
            </label>
            <input
              id="tg-token"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={telegramToken}
              onChange={(e) => setTelegramToken(e.target.value)}
              placeholder={tgTokenConfigured ? "•••••• (enter new value to replace)" : "paste token"}
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-prefix">
              Message prefix (must match start of message); <strong className="text-neutral-300">empty</strong> = no
              prefix (every text message is a prompt)
            </label>
            <input
              id="tg-prefix"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={tgTriggerPrefix}
              onChange={(e) => setTgTriggerPrefix(e.target.value)}
              placeholder="e.g. !agent  — leave empty for no prefix"
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-model">
              Ollama model id (empty = server default)
            </label>
            <input
              id="tg-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={tgChatModel}
              onChange={(e) => setTgChatModel(e.target.value)}
              placeholder="e.g. nemotron-3-nano:4b"
            />
            <button
              type="button"
              className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              disabled={!tgTokenConfigured}
              onClick={() => void clearTelegramToken()}
            >
              Clear Telegram token
            </button>
            <label className="mt-6 block text-xs text-surface-muted" htmlFor="http-client-log-level">
              HTTP-Client-Logging (<span className="font-mono">httpx</span> / Long-Poll) — in{" "}
              <span className="font-mono text-neutral-400">operator_settings</span>, nicht in{" "}
              <span className="font-mono text-neutral-400">.env</span>
            </label>
            <select
              id="http-client-log-level"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={httpClientLogLevel}
              onChange={(e) => setHttpClientLogLevel(e.target.value)}
            >
              <option value="WARNING">WARNING — Standard (ruhig, keine Zeile pro getUpdates)</option>
              <option value="INFO">INFO — jede HTTP-Anfrage loggen (Debug)</option>
              <option value="DEBUG">DEBUG</option>
              <option value="ERROR">ERROR</option>
            </select>
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Scheduler (Agent)</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Periodischer Hintergrund-Check per <span className="font-mono text-neutral-400">chat_completion</span> als
              gewählter User. Bei Bedarf Telegram an dieselbe verknüpfte User-ID — Tageslimit gegen Spam.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={schedulerEnabled}
                onChange={(e) => setSchedulerEnabled(e.target.checked)}
              />
              Scheduler aktivieren
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-interval">
              Intervall (Minuten, 5–1440)
            </label>
            <input
              id="hb-interval"
              type="number"
              min={5}
              max={1440}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerIntervalMin}
              onChange={(e) => setSchedulerIntervalMin(e.target.value)}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-user">
              User (Tenant/Kontext für Tools)
            </label>
            <select
              id="hb-user"
              className="mt-1 w-full max-w-xl rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerUserId}
              onChange={(e) => setSchedulerUserId(e.target.value)}
            >
              <option value="">— wählen —</option>
              {adminUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {(u.email || u.display_name || u.id).trim() || u.id}
                </option>
              ))}
            </select>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-model">
              Modell (leer = Default)
            </label>
            <input
              id="hb-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerModel}
              onChange={(e) => setSchedulerModel(e.target.value)}
              placeholder="z. B. nemotron-3-nano:4b"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-rounds">
              Max. Tool-Runden (leer = Server-Default)
            </label>
            <input
              id="hb-rounds"
              type="number"
              min={1}
              max={64}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerMaxRounds}
              onChange={(e) => setSchedulerMaxRounds(e.target.value)}
              placeholder="z. B. 4"
            />
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={schedulerNotifyOnlyIfNotOk}
                onChange={(e) => setSchedulerNotifyOnlyIfNotOk(e.target.checked)}
              />
              Nur benachrichtigen wenn nicht <span className="font-mono">SCHEDULER_OK</span> / JSON{" "}
              <span className="font-mono">notify:false</span>
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-out">
              Max. ausgehende Meldungen pro Tag (Telegram)
            </label>
            <input
              id="hb-out"
              type="number"
              min={0}
              max={100000}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerMaxOutbound}
              onChange={(e) => setSchedulerMaxOutbound(e.target.value)}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-pkg">
              Tool-Packages (Allowlist, kommagetrennt) — nur bei Modus „allowlist“
            </label>
            <input
              id="hb-pkg"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerPackages}
              onChange={(e) => setSchedulerPackages(e.target.value)}
              placeholder="z. B. clock, openweather"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-llm">
              LLM-Backend
            </label>
            <select
              id="hb-llm"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerLlmBackend}
              onChange={(e) => setSchedulerLlmBackend(e.target.value)}
            >
              <option value="inherit">inherit (Smart-Routing wie Chat)</option>
              <option value="ollama">ollama</option>
              <option value="external">external</option>
            </select>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-tools">
              Tools-Modus
            </label>
            <select
              id="hb-tools"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerToolsMode}
              onChange={(e) => setSchedulerToolsMode(e.target.value)}
            >
              <option value="none">none — nur Text, keine Tools</option>
              <option value="allowlist">allowlist — nur Packages oben</option>
              <option value="full">full — alle erlaubten Tools (Policy)</option>
            </select>
            <p className="mt-4 rounded-md border border-white/10 bg-black/20 px-3 py-2 text-xs text-surface-muted">
              Legacy IDE/PIDEA ist entfernt. Persistierte Jobs:{" "}
              <span className="font-mono text-neutral-400">server_periodic</span> (Chat) und{" "}
              <span className="font-mono text-neutral-400">coding_agent</span> (Coding Agent auf Workspace,{" "}
              <span className="font-mono">workspace_id</span> erforderlich). Worker-Timeout gilt für beide Ziele.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-instr">
              Anweisungen (Prompt)
            </label>
            <textarea
              id="hb-instr"
              rows={4}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={schedulerInstructions}
              onChange={(e) => setSchedulerInstructions(e.target.value)}
              placeholder="Was soll der Scheduler prüfen?"
            />
            <p className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">
              Persistierte Jobs (<span className="font-mono">scheduler_jobs</span>)
            </p>
            <p className="mt-1 text-xs text-surface-muted">
              Hintergrund-Thread für gespeicherte Jobs (<span className="font-mono">server_periodic</span> +{" "}
              <span className="font-mono">coding_agent</span>).
              Einstellungen liegen in der Datenbank (hier), nicht in Umgebungsvariablen.
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={schedulerJobsWorkerEnabled}
                onChange={(e) => setSchedulerJobsWorkerEnabled(e.target.checked)}
              />
              Worker aktiv (Hintergrund-Thread)
            </label>
          </section>

          <section className="mt-6 rounded-lg border border-surface-border p-4">
            <h3 className="text-sm font-medium text-white">Workspaces</h3>
            <p className="mt-1 text-xs text-surface-muted">
              Project workspaces for the Coding Agent.
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={workspaceAllowSelfEditing}
                onChange={(e) => setWorkspaceAllowSelfEditing(e.target.checked)}
              />
              Erlaube Bearbeitung von AgentLayer selbst (Workspace "AgentLayer (self)")
            </label>
            <p className="mt-2 text-xs text-surface-muted">
              Wenn aktiviert, erscheint in der Coding Agent Page ein zusätzlicher Workspace der auf das
              AgentLayer-Verzeichnis (/app) zeigt. Der Agent kann dann das eigene Projekt bearbeiten.
            </p>
          </section>

          <div className="mt-6 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
              onClick={() => void save()}
            >
              Save
            </button>
          </div>
          {saveMsg ? (
            <p className={`mt-3 text-sm ${saveMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
              {saveMsg.text}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
