import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { SETUP_WIZARD_ACTIVE_KEY, useAuth } from "../auth/AuthContext";
import {
  DEFAULT_LLM_PRESET,
  getLlmPreset,
  LLM_PRESETS,
  type LlmPresetId,
} from "../setup/llmPresets";

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

type SetupCatalog = {
  providers: SetupCatalogProvider[];
  embedding: {
    configured?: boolean;
    reachable?: boolean;
    rag_active?: boolean;
    status_line?: string | null;
    model?: string | null;
    detail?: string | null;
    available_models?: string[];
    ollama_opt_in?: {
      available?: boolean;
      suggested_base_url?: string | null;
      suggested_model?: string | null;
      suggested_models?: string[];
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
};

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

export function SetupWizardPage() {
  const navigate = useNavigate();
  const { accessToken, loading, setupStatus, refreshSetupStatus, completeSetup } = useAuth();

  const [step, setStep] = useState(1);
  const [statusLoading, setStatusLoading] = useState(true);

  const [setupToken, setSetupToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminPending, setAdminPending] = useState(false);

  const [catalog, setCatalog] = useState<SetupCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [primaryProviderId, setPrimaryProviderId] = useState("");
  const [modelAgent, setModelAgent] = useState("");
  const [modelCoding, setModelCoding] = useState("");
  const [modelDefault, setModelDefault] = useState("");
  const [ragEmbedding, setRagEmbedding] = useState("");

  const [prefsPending, setPrefsPending] = useState(false);
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [prefsOk, setPrefsOk] = useState<string | null>(null);
  const [embedTestOk, setEmbedTestOk] = useState<string | null>(null);
  const [embedTestPending, setEmbedTestPending] = useState(false);
  const [ollamaEmbedPending, setOllamaEmbedPending] = useState(false);
  const [showManual, setShowManual] = useState(false);

  const [preset, setPreset] = useState<LlmPresetId>(DEFAULT_LLM_PRESET);
  const [baseUrl, setBaseUrl] = useState(getLlmPreset(DEFAULT_LLM_PRESET).baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [modelDefaultManual, setModelDefaultManual] = useState("");
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmPending, setLlmPending] = useState(false);
  const [llmTestOk, setLlmTestOk] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    const s = await refreshSetupStatus();
    setStatusLoading(false);
    return s;
  }, [refreshSetupStatus]);

  const loadCatalog = useCallback(async () => {
    if (!accessToken) return;
    setCatalogLoading(true);
    setCatalogError(null);
    const r = await fetch("/auth/setup/catalog", {
      credentials: "include",
      headers: authHeaders(accessToken),
    });
    setCatalogLoading(false);
    if (!r.ok) {
      let msg = "Katalog konnte nicht geladen werden.";
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
    setPrimaryProviderId(s.primary_provider_id ?? "");
    setModelAgent(s.model_agent ?? "");
    setModelCoding(s.model_coding ?? "");
    setModelDefault(s.model_default ?? "");
    setRagEmbedding(s.rag_embedding_model ?? "");
  }, [accessToken]);

  useEffect(() => {
    void (async () => {
      const s = await loadStatus();
      if (!s) return;
      if (s.needs_admin) return;
      const wizardActive =
        sessionStorage.getItem(SETUP_WIZARD_ACTIVE_KEY) === "1" ||
        s.needs_provider_wizard === true;
      if (wizardActive && accessToken) return;
      if (!accessToken) {
        navigate("/login", { replace: true });
      }
    })();
  }, [loadStatus, navigate, accessToken]);

  useEffect(() => {
    if (!loading && accessToken && setupStatus && !setupStatus.needs_admin) {
      const wizardActive =
        sessionStorage.getItem(SETUP_WIZARD_ACTIVE_KEY) === "1" ||
        setupStatus.needs_provider_wizard === true;
      if (wizardActive && step < 2) {
        setStep(2);
      }
    }
  }, [loading, accessToken, setupStatus, step]);

  useEffect(() => {
    if (step === 2 && accessToken) {
      void loadCatalog();
    }
  }, [step, accessToken, loadCatalog]);

  const selectedProvider = catalog?.providers.find((p) => p.provider_id === primaryProviderId);

  const presetConfig = getLlmPreset(preset);

  function onPresetChange(p: LlmPresetId) {
    const cfg = getLlmPreset(p);
    setPreset(p);
    if (p !== "custom") {
      setBaseUrl(cfg.baseUrl);
      if (cfg.modelExample) {
        setModelDefaultManual(cfg.modelExample);
      }
    }
    setLlmTestOk(null);
    setLlmError(null);
  }

  async function onAdminSubmit(e: FormEvent) {
    e.preventDefault();
    setAdminPending(true);
    setAdminError(null);
    const result = await completeSetup(email.trim(), password, passwordConfirm, setupToken);
    setAdminPending(false);
    if (!result.ok) {
      setAdminError(result.error ?? "Einrichtung fehlgeschlagen.");
      return;
    }
    sessionStorage.setItem(SETUP_WIZARD_ACTIVE_KEY, "1");
    await refreshSetupStatus();
    setStep(2);
  }

  function finishWizard() {
    sessionStorage.removeItem(SETUP_WIZARD_ACTIVE_KEY);
  }

  async function onSkipProfiles() {
    if (!accessToken) return;
    setPrefsPending(true);
    setPrefsError(null);
    const r = await fetch("/auth/setup/skip-profiles", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
    });
    setPrefsPending(false);
    if (!r.ok) {
      let msg = "Überspringen fehlgeschlagen.";
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setPrefsError(msg);
      return;
    }
    finishWizard();
    await refreshSetupStatus();
    setStep(3);
  }

  async function onSavePreferences(e: FormEvent) {
    e.preventDefault();
    if (!accessToken) {
      setPrefsError("Sitzung abgelaufen. Laden Sie die Seite neu.");
      return;
    }
    if (!primaryProviderId) {
      setPrefsError("Bitte einen Provider auswählen.");
      return;
    }
    setPrefsPending(true);
    setPrefsError(null);
    setPrefsOk(null);
    const r = await fetch("/auth/setup/preferences", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        primary_provider_id: primaryProviderId,
        model_agent: modelAgent.trim() || null,
        model_coding: modelCoding.trim() || null,
        model_default: modelDefault.trim() || null,
        rag_embedding_model: ragEmbedding.trim() || null,
      }),
    });
    setPrefsPending(false);
    if (!r.ok) {
      let msg = "Speichern fehlgeschlagen.";
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setPrefsError(msg);
      return;
    }
    setPrefsOk("Standard-Provider und Profilmodelle gespeichert.");
    finishWizard();
    await refreshSetupStatus();
    setStep(3);
  }

  async function onEnableOllamaEmbedding() {
    if (!accessToken) return;
    setOllamaEmbedPending(true);
    setPrefsError(null);
    const r = await fetch("/auth/setup/enable-ollama-embedding", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
    });
    setOllamaEmbedPending(false);
    if (!r.ok) {
      let msg = "Ollama-Embedding konnte nicht aktiviert werden.";
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setPrefsError(msg);
      return;
    }
    const d = (await r.json()) as {
      rag_embedding_model?: string;
      embedding?: SetupCatalog["embedding"];
    };
    if (d.rag_embedding_model) setRagEmbedding(d.rag_embedding_model);
    await loadCatalog();
  }

  async function onTestEmbedding() {
    if (!accessToken || !ragEmbedding.trim()) return;
    setEmbedTestPending(true);
    setEmbedTestOk(null);
    setPrefsError(null);
    const r = await fetch("/auth/setup/test-embedding", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({ model: ragEmbedding.trim() }),
    });
    setEmbedTestPending(false);
    if (!r.ok) {
      let msg = "Embedding-Test fehlgeschlagen.";
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setPrefsError(msg);
      return;
    }
    const d = (await r.json()) as { embedding_dim?: number };
    setEmbedTestOk(
      d.embedding_dim != null
        ? `Embedding OK (${d.embedding_dim} Dimensionen).`
        : "Embedding OK."
    );
  }

  async function llmRequest(testOnly: boolean): Promise<boolean> {
    if (!accessToken) {
      setLlmError("Sitzung abgelaufen. Laden Sie die Seite neu.");
      return false;
    }
    const cfg = getLlmPreset(preset);
    if (cfg.apiKeyRequired && !apiKey.trim()) {
      setLlmError(`API-Schlüssel erforderlich (${cfg.endpointLabel}).`);
      return false;
    }
    if (!baseUrl.trim()) {
      setLlmError("Basis-URL ist erforderlich.");
      return false;
    }
    setLlmPending(true);
    setLlmError(null);
    setLlmTestOk(null);
    const r = await fetch("/auth/setup/llm", {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || null,
        model_default: modelDefaultManual.trim() || null,
        label: cfg.endpointLabel,
        test_only: testOnly,
      }),
    });
    setLlmPending(false);
    if (!r.ok) {
      let msg = "Anfrage fehlgeschlagen.";
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setLlmError(msg);
      return false;
    }
    const d = (await r.json()) as { model_count?: number; ok?: boolean };
    const n = d.model_count ?? 0;
    if (n === 0 && !testOnly) {
      setLlmError(
        "Verbindung OK, aber keine Modelle gemeldet. Prüfen Sie den Endpunkt oder wählen Sie ein Modell aus der Liste."
      );
      return false;
    }
    setLlmTestOk(
      n > 0
        ? `Verbindung erfolgreich. ${n} Modell${n === 1 ? "" : "e"} verfügbar.`
        : "Verbindung erfolgreich."
    );
    if (!testOnly) {
      await loadCatalog();
    }
    return true;
  }

  async function onLlmTest(ev: FormEvent) {
    ev.preventDefault();
    await llmRequest(true);
  }

  async function onLlmSave(ev: FormEvent) {
    ev.preventDefault();
    await llmRequest(false);
  }

  if (statusLoading || loading) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center text-sm text-surface-muted">
        Laden…
      </div>
    );
  }

  if (setupStatus && !setupStatus.needs_setup && !accessToken) {
    return null;
  }

  const chatModels = selectedProvider?.chat_models ?? [];
  const embedModelsOnProvider = selectedProvider?.embedding_models ?? [];
  const embedCatalogModels = catalog?.embedding.available_models ?? [];
  const embedOptions = [
    ...new Set([
      ...embedModelsOnProvider,
      ...embedCatalogModels,
      ...(catalog?.embedding.model ? [catalog.embedding.model] : []),
    ]),
  ].filter(Boolean);

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-lg px-6 py-12">
        <p className="text-xs font-medium uppercase tracking-wide text-surface-muted">
          Schritt {step} von 3
        </p>

        {step === 1 ? (
          <>
            <h1 className="mt-2 text-2xl font-semibold text-white">Ersteinrichtung</h1>
            <p className="mt-2 text-sm text-surface-muted">
              Legen Sie das Administrator-Konto für diese Instanz an.
            </p>
            <form onSubmit={onAdminSubmit} className="mt-8 flex flex-col gap-4">
              {setupStatus?.setup_token_required ? (
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-surface-muted">Einrichtungs-Token</span>
                  <input
                    type="password"
                    name="setup_token"
                    autoComplete="off"
                    value={setupToken}
                    onChange={(ev) => setSetupToken(ev.target.value)}
                    required
                    className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  <p className="text-xs text-surface-muted">
                    {setupStatus.setup_token_source === "env"
                      ? "Wert aus AGENT_SETUP_TOKEN in der Server-Konfiguration (.env)."
                      : "Einmalig im Server-Log nach Start (z. B. docker compose logs agent-layer)."}
                  </p>
                </label>
              ) : null}
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-surface-muted">E-Mail</span>
                <input
                  type="email"
                  name="email"
                  autoComplete="username"
                  value={email}
                  onChange={(ev) => setEmail(ev.target.value)}
                  required
                  className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-surface-muted">Passwort</span>
                <input
                  type="password"
                  name="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(ev) => setPassword(ev.target.value)}
                  required
                  minLength={8}
                  className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-surface-muted">Passwort bestätigen</span>
                <input
                  type="password"
                  name="password_confirm"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  onChange={(ev) => setPasswordConfirm(ev.target.value)}
                  required
                  minLength={8}
                  className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </label>
              <p className="text-xs text-surface-muted">
                Mindestens 8 Zeichen. Weitere Konten legen Sie unter Admin → Benutzer an.
              </p>
              {adminError ? (
                <p className="text-sm text-red-400" role="alert">
                  {adminError}
                </p>
              ) : null}
              <button
                type="submit"
                disabled={adminPending}
                className="rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {adminPending ? "Wird angelegt…" : "Weiter"}
              </button>
            </form>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <h1 className="mt-2 text-2xl font-semibold text-white">KI-Provider &amp; Modelle</h1>
            <p className="mt-2 text-sm text-surface-muted">
              Erkannte Provider aus Umgebung und Konfiguration. Chat- und Embedding-Modelle werden
              automatisch eingestuft; Sie legen hier einmal die Standard-Profile fest. Cloud-Anbieter
              (OpenAI, Claude via OpenRouter, Groq, …) binden Sie unten als OpenAI-kompatiblen
              Endpunkt ein. Im Chat und unter Admin können Sie jederzeit andere Modelle wählen.
            </p>

            {catalogLoading ? (
              <p className="mt-6 text-sm text-surface-muted">Provider werden geprüft…</p>
            ) : null}
            {catalogError ? (
              <p className="mt-4 text-sm text-red-400" role="alert">
                {catalogError}
              </p>
            ) : null}

            {catalog ? (
              <div className="mt-6 space-y-4">
                <section>
                  <h2 className="text-sm font-medium text-white">Provider-Status</h2>
                  <ul className="mt-2 space-y-2">
                    {catalog.providers.map((p) => (
                      <li
                        key={p.provider_id}
                        className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-white">{p.label}</span>
                          <span
                            className={
                              p.reachable ? "text-emerald-400" : "text-amber-400"
                            }
                          >
                            {p.reachable ? "Erreichbar" : "Nicht erreichbar"}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-surface-muted">
                          {p.source}
                          {p.model_count > 0
                            ? ` · ${p.chat_models.length} Chat, ${p.embedding_models.length} Embedding`
                            : ""}
                        </p>
                        {p.detail && !p.reachable ? (
                          <p className="mt-1 text-xs text-amber-300/90">{p.detail}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-white">Embeddings (RAG / Memory)</span>
                    <span
                      className={
                        catalog.embedding.configured && catalog.embedding.reachable
                          ? "text-emerald-400"
                          : "text-amber-400"
                      }
                    >
                      {!catalog.embedding.configured
                        ? "Optional"
                        : catalog.embedding.reachable
                          ? "Erreichbar"
                          : "Nicht erreichbar"}
                    </span>
                  </div>
                  {catalog.embedding.status_line && !catalog.embedding.configured ? (
                    <p className="mt-2 text-xs text-surface-muted">{catalog.embedding.status_line}</p>
                  ) : null}
                  {catalog.embedding.configured && catalog.embedding.detail && !catalog.embedding.reachable ? (
                    <p className="mt-1 text-xs text-amber-300/90">{catalog.embedding.detail}</p>
                  ) : null}
                  {!catalog.embedding.configured &&
                  catalog.embedding.ollama_opt_in?.available ? (
                    <div className="mt-3 flex flex-col gap-2">
                      <p className="text-xs text-surface-muted">
                        Ein Anbieter, zwei Pfade: Chat läuft über Ollama; für RAG dieselbe URL für{" "}
                        <span className="font-mono">/v1/embeddings</span> (ohne .env-Neustart).
                        Modell-Vorschlag:{" "}
                        <span className="font-mono text-white">
                          {catalog.embedding.ollama_opt_in.suggested_model ?? "nomic-embed-text"}
                        </span>
                      </p>
                      <button
                        type="button"
                        disabled={ollamaEmbedPending || prefsPending}
                        onClick={() => void onEnableOllamaEmbedding()}
                        className="self-start rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-sm text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
                      >
                        {ollamaEmbedPending
                          ? "Wird eingerichtet…"
                          : "Ollama auch für Embeddings (RAG) nutzen"}
                      </button>
                    </div>
                  ) : null}
                </section>

                <form onSubmit={onSavePreferences} className="flex flex-col gap-4">
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Bevorzugter Chat-Provider</span>
                    <select
                      value={primaryProviderId}
                      onChange={(ev) => {
                        const id = ev.target.value;
                        setPrimaryProviderId(id);
                        const prov = catalog.providers.find((x) => x.provider_id === id);
                        if (prov?.chat_models[0]) {
                          setModelAgent(prov.chat_models[0]);
                          setModelDefault(prov.chat_models[0]);
                          setModelCoding(prov.chat_models[1] ?? prov.chat_models[0]);
                        }
                      }}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    >
                      <option value="">— auswählen —</option>
                      {catalog.providers.map((p) => (
                        <option
                          key={p.provider_id}
                          value={p.provider_id}
                          disabled={!p.reachable}
                        >
                          {p.label}
                          {p.reachable ? "" : " (offline)"}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Allgemein / Agent (Chat)</span>
                    <select
                      value={modelAgent}
                      onChange={(ev) => setModelAgent(ev.target.value)}
                      disabled={!chatModels.length}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50"
                    >
                      {chatModels.length === 0 ? (
                        <option value="">Keine Chat-Modelle</option>
                      ) : (
                        chatModels.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))
                      )}
                    </select>
                  </label>

                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Coding-Agent</span>
                    <select
                      value={modelCoding}
                      onChange={(ev) => setModelCoding(ev.target.value)}
                      disabled={!chatModels.length}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50"
                    >
                      {chatModels.map((m) => (
                        <option key={`c-${m}`} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Standard-Fallback (Chat)</span>
                    <select
                      value={modelDefault}
                      onChange={(ev) => setModelDefault(ev.target.value)}
                      disabled={!chatModels.length}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50"
                    >
                      {chatModels.map((m) => (
                        <option key={`d-${m}`} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>

                  {embedOptions.length > 0 || catalog.embedding.configured ? (
                    <div className="flex flex-col gap-2">
                      <label className="flex flex-col gap-1.5 text-sm">
                        <span className="text-surface-muted">
                          RAG / Embedding-Modell
                          {!catalog.embedding.configured ? " (nach Aktivierung oben)" : ""}
                        </span>
                        <select
                          value={ragEmbedding}
                          onChange={(ev) => setRagEmbedding(ev.target.value)}
                          className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                        >
                          <option value="">— optional —</option>
                          {embedOptions.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        disabled={embedTestPending || !ragEmbedding.trim()}
                        onClick={() => void onTestEmbedding()}
                        className="self-start rounded-lg border border-surface-border px-3 py-2 text-sm text-white hover:bg-white/5 disabled:opacity-50"
                      >
                        {embedTestPending ? "Test läuft…" : "Embedding testen"}
                      </button>
                      {embedTestOk ? (
                        <p className="text-sm text-emerald-400" role="status">
                          {embedTestOk}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {prefsError ? (
                    <p className="text-sm text-red-400" role="alert">
                      {prefsError}
                    </p>
                  ) : null}
                  {prefsOk ? (
                    <p className="text-sm text-emerald-400" role="status">
                      {prefsOk}
                    </p>
                  ) : null}

                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      disabled={catalogLoading}
                      onClick={() => void loadCatalog()}
                      className="rounded-lg border border-surface-border px-4 py-2.5 text-sm text-white hover:bg-white/5 disabled:opacity-50"
                    >
                      Aktualisieren
                    </button>
                    <button
                      type="submit"
                      disabled={
                        prefsPending ||
                        !primaryProviderId ||
                        !selectedProvider?.reachable
                      }
                      className="rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    >
                      {prefsPending ? "Wird gespeichert…" : "Speichern & weiter"}
                    </button>
                  </div>
                </form>
              </div>
            ) : null}

            <div className="mt-8 border-t border-surface-border pt-6">
              <button
                type="button"
                onClick={() => setShowManual((v) => !v)}
                className="text-sm text-sky-400 hover:underline"
              >
                {showManual
                  ? "Cloud-/Zusatz-Endpunkt ausblenden"
                  : "Cloud- oder Zusatz-Endpunkt hinzufügen (OpenAI, OpenRouter, …)"}
              </button>
              {showManual ? (
                <form onSubmit={onLlmSave} className="mt-4 flex flex-col gap-4">
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Vorlage</span>
                    <select
                      value={preset}
                      onChange={(ev) => onPresetChange(ev.target.value as LlmPresetId)}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    >
                      {LLM_PRESETS.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-surface-muted">{presetConfig.help}</p>
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Basis-URL</span>
                    <input
                      type="url"
                      value={baseUrl}
                      onChange={(ev) => {
                        setBaseUrl(ev.target.value);
                        setPreset("custom");
                        setLlmTestOk(null);
                      }}
                      required
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">
                      API-Schlüssel
                      {presetConfig.apiKeyRequired ? " (erforderlich)" : " (optional)"}
                    </span>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(ev) => {
                        setApiKey(ev.target.value);
                        setLlmTestOk(null);
                      }}
                      autoComplete="off"
                      required={presetConfig.apiKeyRequired}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    />
                    <p className="text-xs text-surface-muted">{presetConfig.apiKeyHint}</p>
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-surface-muted">Standardmodell (optional)</span>
                    <input
                      type="text"
                      value={modelDefaultManual}
                      onChange={(ev) => setModelDefaultManual(ev.target.value)}
                      placeholder={presetConfig.modelPlaceholder}
                      className="rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-white focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    />
                  </label>
                  {llmError ? (
                    <p className="text-sm text-red-400" role="alert">
                      {llmError}
                    </p>
                  ) : null}
                  {llmTestOk ? (
                    <p className="text-sm text-emerald-400" role="status">
                      {llmTestOk}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      disabled={llmPending}
                      onClick={(ev) => void onLlmTest(ev as unknown as FormEvent)}
                      className="rounded-lg border border-surface-border px-4 py-2.5 text-sm text-white hover:bg-white/5 disabled:opacity-50"
                    >
                      Verbindung prüfen
                    </button>
                    <button
                      type="submit"
                      disabled={llmPending}
                      className="rounded-lg border border-surface-border px-4 py-2.5 text-sm text-white hover:bg-white/5 disabled:opacity-50"
                    >
                      Endpunkt speichern
                    </button>
                  </div>
                </form>
              ) : null}
            </div>

            <button
              type="button"
              disabled={prefsPending}
              onClick={() => void onSkipProfiles()}
              className="mt-6 text-left text-sm text-surface-muted hover:text-white disabled:opacity-50"
            >
              Überspringen (Vorschläge übernehmen, falls erreichbar)
            </button>
          </>
        ) : null}

        {step === 3 ? (
          <>
            <h1 className="mt-2 text-2xl font-semibold text-white">Einrichtung abgeschlossen</h1>
            <p className="mt-2 text-sm text-surface-muted">
              Die Instanz ist betriebsbereit. Im Chat wählen Sie das Modell im Composer; Profile und
              Endpunkte passen Sie unter Admin → Schnittstellen an.
            </p>
            <div className="mt-8 flex flex-col gap-3">
              <Link
                to="/chat"
                className="rounded-lg bg-sky-600 px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-sky-500"
              >
                Zum Chat
              </Link>
              <Link
                to="/admin"
                className="rounded-lg border border-surface-border px-4 py-2.5 text-center text-sm text-white hover:bg-white/5"
              >
                Admin-Bereich
              </Link>
            </div>
          </>
        ) : null}

        <p className="mt-10 text-center text-sm text-surface-muted">
          <Link to="/login" className="text-sky-400 hover:underline">
            Zur Anmeldung
          </Link>
        </p>
      </div>
    </div>
  );
}
