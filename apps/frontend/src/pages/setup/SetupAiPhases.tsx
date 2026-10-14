/**
 * Setup wizard AI: endpoints → RAG → voice → coding runtime.
 * Preferred provider + default model live on the chat endpoint card (step 1).
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Select } from "../../ui/Field";
import { Button } from "../../ui/Button";
import { Checkbox } from "../../ui/Checkbox";
import { SetupProviderEndpointsPanel } from "./SetupProviderEndpointsPanel";

export type AiPhase = "endpoints" | "rag" | "voice" | "coding";

const AI_PHASES: AiPhase[] = ["endpoints", "rag", "voice", "coding"];

type SetupCatalogProvider = {
  provider_id: string;
  label: string;
  source: string;
  reachable: boolean;
  detail?: string | null;
  chat_models: string[];
  embedding_models: string[];
  model_count: number;
};

type VoiceProvider = { provider_id: string; label: string; source: string };

type SetupCatalog = {
  providers: SetupCatalogProvider[];
  embedding: {
    configured?: boolean;
    reachable?: boolean;
    status_line?: string | null;
    model?: string | null;
    detail?: string | null;
    available_models?: string[];
    chat_embed_opt_in?: {
      available?: boolean;
      suggested_model?: string | null;
    };
  };
  suggestions: {
    primary_provider_id?: string | null;
    model_agent?: string | null;
    model_coding?: string | null;
    model_default?: string | null;
    rag_embedding_model?: string | null;
  };
  any_chat_reachable: boolean;
  voice?: {
    stt_providers: VoiceProvider[];
    tts_providers: VoiceProvider[];
    voice_enabled?: boolean;
    voice_stt_provider_id?: string | null;
    voice_tts_provider_id?: string | null;
    voice_stt_model?: string | null;
    voice_tts_model?: string | null;
  };
  external_runtimes?: {
    enabled: boolean;
    env_enabled: boolean;
    db_override: boolean | null;
    qwen_enabled: boolean;
    qwen_env_enabled: boolean;
    qwen_db_override: boolean | null;
    dsh_enabled?: boolean;
    preferred_id?: string | null;
    packages?: Array<{
      id: string;
      label: string;
      installed?: boolean;
      version?: string | null;
      npm_package?: string;
    }>;
    runtimes: Array<{ id: string; available: boolean; reason: string }>;
  };
};

const CODING_RUNTIME_IDS = ["qwen_code", "deepseek_harness"] as const;
type CodingRuntimeId = (typeof CODING_RUNTIME_IDS)[number];

const CODING_RUNTIME_NPM: Record<CodingRuntimeId, string> = {
  qwen_code: "@qwen-code/qwen-code",
  deepseek_harness: "@deepseek-ai/dsh",
};

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function isDbSource(source: string | undefined): boolean {
  const s = String(source || "").toLowerCase();
  return s === "db" || s.startsWith("db") || s.includes("operator");
}

type Props = {
  accessToken: string;
  onComplete: () => void;
};

export function SetupAiPhases({ accessToken, onComplete }: Props) {
  const { t } = useTranslation(["setup"]);
  const [phase, setPhase] = useState<AiPhase>("endpoints");
  const phaseIndex = AI_PHASES.indexOf(phase);

  const [catalog, setCatalog] = useState<SetupCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [ragEmbedding, setRagEmbedding] = useState("");
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [chatEmbedPending, setChatEmbedPending] = useState(false);
  const [continuePending, setContinuePending] = useState(false);

  const [voiceSttId, setVoiceSttId] = useState("");
  const [voiceTtsId, setVoiceTtsId] = useState("");
  const [voicePending, setVoicePending] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const [enabledRuntimes, setEnabledRuntimes] = useState<Set<CodingRuntimeId>>(new Set());
  const [preferredRuntime, setPreferredRuntime] = useState<"" | CodingRuntimeId>("");
  const [runtimePending, setRuntimePending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [runtimeLog, setRuntimeLog] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    const r = await fetch("/auth/setup/catalog", {
      credentials: "include",
      headers: authHeaders(accessToken),
    });
    setCatalogLoading(false);
    if (!r.ok) {
      let msg = t("setup:catalogLoadFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setCatalogError(msg);
      return;
    }
    const data = (await r.json()) as SetupCatalog;
    setCatalog(data);
    const s = data.suggestions;
    setRagEmbedding((prev) => prev || s.rag_embedding_model || "");
    if (data.voice) {
      setVoiceSttId(data.voice.voice_stt_provider_id || "");
      setVoiceTtsId(data.voice.voice_tts_provider_id || "");
    }
    if (data.external_runtimes) {
      const next = new Set<CodingRuntimeId>();
      if (data.external_runtimes.qwen_enabled) next.add("qwen_code");
      if (data.external_runtimes.dsh_enabled) next.add("deepseek_harness");
      setEnabledRuntimes(next);
      const pref = (data.external_runtimes.preferred_id || "").trim();
      setPreferredRuntime(
        pref === "qwen_code" || pref === "deepseek_harness" ? pref : ""
      );
    }
  }, [accessToken, t]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const dbProviders = (catalog?.providers ?? []).filter((p) => isDbSource(p.source));
  // Prefer DB endpoints only — never Continue with an env provider_id when DB rows exist
  // (that path used to upsert a second host twin).
  const chatProviders = dbProviders.length > 0 ? dbProviders : (catalog?.providers ?? []);
  const primaryProvider =
    chatProviders.find((p) => p.reachable && p.provider_id.startsWith("provider_db_")) ||
    chatProviders.find((p) => p.provider_id.startsWith("provider_db_")) ||
    chatProviders.find((p) => p.provider_id === catalog?.suggestions.primary_provider_id) ||
    chatProviders.find((p) => p.reachable) ||
    chatProviders[0];
  const defaultChatModel =
    catalog?.suggestions.model_default || primaryProvider?.chat_models[0] || "";
  const dbStt = (catalog?.voice?.stt_providers ?? []).filter((p) => isDbSource(p.source));
  const dbTts = (catalog?.voice?.tts_providers ?? []).filter((p) => isDbSource(p.source));
  const sttOptions = dbStt.length > 0 ? dbStt : (catalog?.voice?.stt_providers ?? []);
  const ttsOptions = dbTts.length > 0 ? dbTts : (catalog?.voice?.tts_providers ?? []);

  const dbChatReachable = Boolean(
    catalog?.any_chat_reachable ||
      chatProviders.some((p) => p.reachable && p.chat_models.length > 0)
  );

  function goNext() {
    const i = AI_PHASES.indexOf(phase);
    if (i < AI_PHASES.length - 1) setPhase(AI_PHASES[i + 1]!);
    else onComplete();
  }

  function goBack() {
    const i = AI_PHASES.indexOf(phase);
    if (i > 0) setPhase(AI_PHASES[i - 1]!);
  }

  async function onContinueFromEndpoints() {
    // If DB already has chat endpoints, Continue must NOT call preferences upsert
    // (old backend paths invented a second host twin + ranked model). Just proceed.
    if (dbProviders.length > 0) {
      setPrefsError(null);
      goNext();
      return;
    }
    const pid = primaryProvider?.provider_id;
    if (!pid) {
      setPrefsError(t("setup:prefsChooseProvider"));
      return;
    }
    setContinuePending(true);
    setPrefsError(null);
    const r = await fetch("/auth/setup/preferences", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({ primary_provider_id: pid }),
    });
    setContinuePending(false);
    if (!r.ok) {
      let msg = t("setup:saveFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setPrefsError(msg);
      return;
    }
    goNext();
  }

  async function onEnableChatEmbed() {
    setChatEmbedPending(true);
    setPrefsError(null);
    const r = await fetch("/auth/setup/enable-chat-provider-embedding", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
    });
    setChatEmbedPending(false);
    if (!r.ok) {
      setPrefsError(t("setup:chatEmbedEnableFailed"));
      return;
    }
    const d = (await r.json()) as { rag_embedding_model?: string };
    if (d.rag_embedding_model) setRagEmbedding(d.rag_embedding_model);
    await loadCatalog();
  }

  async function onSaveVoice() {
    setVoicePending(true);
    setVoiceError(null);
    // Primary card = first DB/catalog option — no second dropdown below the endpoint panels.
    const stt = voiceSttId || sttOptions[0]?.provider_id || "";
    const tts = voiceTtsId || ttsOptions[0]?.provider_id || "";
    const r = await fetch("/v1/admin/operator-settings", {
      method: "PATCH",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        voice_enabled: Boolean(stt || tts),
        voice_stt_provider_id: stt || null,
        voice_tts_provider_id: tts || null,
      }),
    });
    setVoicePending(false);
    if (!r.ok) {
      setVoiceError(t("setup:voiceSaveFailed"));
      return;
    }
    goNext();
  }

  function toggleRuntime(id: CodingRuntimeId, on: boolean) {
    setEnabledRuntimes((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setPreferredRuntime((prev) => {
      if (!on && prev === id) return "";
      if (on && !prev) return id;
      return prev;
    });
  }

  async function onSaveRuntime() {
    setRuntimePending(true);
    setRuntimeError(null);
    setRuntimeLog(null);
    const enabled = [...enabledRuntimes];
    for (const id of enabled) {
      const pkg = catalog?.external_runtimes?.packages?.find((p) => p.id === id);
      if (pkg?.installed) continue;
      const ir = await fetch(`/v1/admin/coding-runtimes/${id}/install`, {
        method: "POST",
        credentials: "include",
        headers: authHeaders(accessToken),
        body: JSON.stringify({ version: "latest" }),
      });
      const body = (await ir.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        log?: string;
        detail?: string;
      };
      if (!ir.ok || body.ok === false) {
        setRuntimePending(false);
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : ir.status === 404
              ? t("setup:runtimeApiMissing")
              : body.error || t("setup:runtimeInstallFailed", { id });
        setRuntimeError(detail);
        if (body.log) setRuntimeLog(body.log);
        return;
      }
      if (body.log) setRuntimeLog(body.log);
    }
    const preferred =
      preferredRuntime && enabledRuntimes.has(preferredRuntime) ? preferredRuntime : "";
    const r = await fetch("/v1/admin/coding-runtimes", {
      method: "PATCH",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        enabled_ids: enabled,
        preferred_id: preferred,
      }),
    });
    setRuntimePending(false);
    if (!r.ok) {
      let msg = t("setup:runtimeSaveFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string" && d.detail.trim()) msg = d.detail;
      } catch {
        /* ignore */
      }
      setRuntimeError(msg);
      return;
    }
    onComplete();
  }

  return (
    <div className="mt-base">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {t("setup:aiPhaseOf", { step: phaseIndex + 1, total: AI_PHASES.length })}
      </p>
      <h1 className="mt-base text-2xl font-semibold text-ink-primary">
        {t(`setup:aiPhase_${phase}_title`)}
      </h1>
      <p className="mt-base text-sm text-ink-muted">{t(`setup:aiPhase_${phase}_intro`)}</p>

      {catalogLoading ? (
        <p className="mt-broad text-sm text-ink-muted">{t("setup:catalogLoading")}</p>
      ) : null}
      {catalogError ? (
        <p className="mt-wide text-sm text-danger" role="alert">
          {catalogError}
        </p>
      ) : null}

      {phase === "endpoints" ? (
        <div className="mt-broad space-y-wide">
          <SetupProviderEndpointsPanel
            kind="chat"
            accessToken={accessToken}
            allowPrimary
            defaultName="Chat"
            onChanged={() => void loadCatalog()}
          />
          {prefsError ? (
            <p className="text-sm text-danger" role="alert">
              {prefsError}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-soft">
            <Button
              variant="primary"
              size="lg"
              type="button"
              disabled={!dbChatReachable || continuePending}
              onClick={() => void onContinueFromEndpoints()}
              className="px-wide py-firm text-sm"
            >
              {continuePending ? t("setup:savePending") : t("setup:continueBtn")}
            </Button>
          </div>
          {!dbChatReachable ? (
            <p className="text-xs text-ink-muted">{t("setup:needReachableChat")}</p>
          ) : null}
        </div>
      ) : null}

      {phase === "rag" ? (
        <div className="mt-broad flex flex-col gap-wide">
          <SetupProviderEndpointsPanel
            kind="embedding"
            accessToken={accessToken}
            allowPrimary
            defaultName="Embedding"
            onChanged={() => void loadCatalog()}
          />
          {!catalog?.embedding.configured && catalog?.embedding.chat_embed_opt_in?.available ? (
            <Button
              type="button"
              disabled={chatEmbedPending}
              onClick={() => void onEnableChatEmbed()}
              className="self-start border-accent/40 px-soft py-base text-sm text-badge-accent"
            >
              {chatEmbedPending ? t("setup:chatEmbedPending") : t("setup:chatEmbedBtn")}
            </Button>
          ) : null}
          {prefsError ? (
            <p className="text-sm text-danger" role="alert">
              {prefsError}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-soft">
            <Button type="button" onClick={goBack} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:backBtn")}
            </Button>
            <Button type="button" onClick={goNext} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:skipOptional")}
            </Button>
            <Button
              variant="primary"
              size="lg"
              type="button"
              onClick={goNext}
              className="px-wide py-firm text-sm"
            >
              {t("setup:continueBtn")}
            </Button>
          </div>
        </div>
      ) : null}

      {phase === "voice" ? (
        <div className="mt-broad flex flex-col gap-wide">
          <SetupProviderEndpointsPanel
            kind="voice_stt"
            accessToken={accessToken}
            allowPrimary
            defaultName="STT"
            onChanged={() => void loadCatalog()}
          />
          <SetupProviderEndpointsPanel
            kind="voice_tts"
            accessToken={accessToken}
            allowPrimary
            defaultName="TTS"
            onChanged={() => void loadCatalog()}
          />
          <p className="text-xs text-ink-muted">{t("setup:voiceHint")}</p>
          {voiceError ? (
            <p className="text-sm text-danger" role="alert">
              {voiceError}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-soft">
            <Button type="button" onClick={goBack} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:backBtn")}
            </Button>
            <Button type="button" onClick={goNext} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:skipOptional")}
            </Button>
            <Button
              variant="primary"
              size="lg"
              type="button"
              disabled={voicePending}
              onClick={() => void onSaveVoice()}
              className="px-wide py-firm text-sm"
            >
              {voicePending ? t("setup:savePending") : t("setup:saveAndContinue")}
            </Button>
          </div>
        </div>
      ) : null}

      {phase === "coding" ? (
        <div className="mt-broad flex flex-col gap-wide">
          <p className="rounded-card border border-line bg-card px-soft py-base text-sm text-ink-muted">
            {defaultChatModel
              ? t("setup:codingUsesChatModel", { model: defaultChatModel })
              : t("setup:codingUsesChatModelFallback")}
          </p>
          <p className="text-sm text-ink-muted">{t("setup:runtimeMultiselectHint")}</p>
          <fieldset className="space-y-soft">
            {CODING_RUNTIME_IDS.map((id) => {
              const pkg = catalog?.external_runtimes?.packages?.find((p) => p.id === id);
              const rt = catalog?.external_runtimes?.runtimes?.find((r) => r.id === id);
              const label =
                pkg?.label ||
                (id === "qwen_code" ? t("setup:runtimeQwenTitle") : t("setup:runtimeDshTitle"));
              return (
                <label
                  key={id}
                  className="flex cursor-pointer items-start gap-soft rounded-card border border-line p-wide"
                >
                  <Checkbox
                    checked={enabledRuntimes.has(id)}
                    onChange={(ev) => toggleRuntime(id, ev.target.checked)}
                    className="mt-tight"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink-primary">{label}</span>
                    <span className="mt-tight block text-xs text-ink-muted">
                      {id === "qwen_code"
                        ? t("setup:runtimeQwenDesc")
                        : t("setup:runtimeDshDesc")}
                    </span>
                    <span className="mt-tight block text-xs text-ink-muted">
                      {pkg?.installed
                        ? t("setup:runtimeInstalled", {
                            version: pkg.version || "—",
                          })
                        : t("setup:runtimeWillInstall", {
                            pkg: pkg?.npm_package || CODING_RUNTIME_NPM[id],
                          })}
                      {rt
                        ? ` · ${rt.available ? t("setup:reachable") : rt.reason || t("setup:notReachable")}`
                        : null}
                    </span>
                  </span>
                </label>
              );
            })}
          </fieldset>
          {enabledRuntimes.size > 0 ? (
            <label className="flex flex-col gap-snug text-sm">
              <span className="text-ink-muted">{t("setup:runtimePreferred")}</span>
              <Select
                value={preferredRuntime}
                onChange={(ev) =>
                  setPreferredRuntime(
                    ev.target.value === "qwen_code" || ev.target.value === "deepseek_harness"
                      ? ev.target.value
                      : ""
                  )
                }
              >
                <option value="">{t("setup:runtimePreferredInternal")}</option>
                {[...enabledRuntimes].map((id) => (
                  <option key={id} value={id}>
                    {catalog?.external_runtimes?.packages?.find((p) => p.id === id)?.label || id}
                  </option>
                ))}
              </Select>
            </label>
          ) : null}
          {runtimeError ? (
            <p className="text-sm text-danger" role="alert">
              {runtimeError}
            </p>
          ) : null}
          {runtimeLog ? (
            <pre className="max-h-40 overflow-auto rounded-card border border-line bg-card p-soft text-xs text-ink-muted whitespace-pre-wrap">
              {runtimeLog}
            </pre>
          ) : null}
          <div className="flex flex-wrap gap-soft">
            <Button type="button" onClick={goBack} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:backBtn")}
            </Button>
            <Button type="button" onClick={onComplete} className="px-wide py-firm text-sm hover:bg-white/5">
              {t("setup:skipOptional")}
            </Button>
            <Button
              variant="primary"
              size="lg"
              type="button"
              disabled={runtimePending}
              onClick={() => void onSaveRuntime()}
              className="px-wide py-firm text-sm"
            >
              {runtimePending ? t("setup:runtimeInstallPending") : t("setup:finishAiSetup")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
