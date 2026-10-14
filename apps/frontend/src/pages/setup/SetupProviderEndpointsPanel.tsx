/**
 * Shared setup UI for chat / embedding / voice_stt / voice_tts endpoints.
 * Same bootstrap for every kind: auto-import env → fill URL → probe models → default model.
 */
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DEFAULT_LLM_PRESET,
  getPresetForKind,
  listPresetsForKind,
  type LlmPresetId,
} from "../../setup/llmPresets";
import { Select, TextInput } from "../../ui/Field";
import { Button } from "../../ui/Button";

export type ProviderEndpointKind = "chat" | "embedding" | "voice_stt" | "voice_tts";

type EndpointRow = {
  id: number;
  provider_id?: string;
  label: string;
  base_url: string;
  model_default?: string | null;
  api_key_configured?: boolean;
  api_header_name?: string;
  sort_order?: number;
  models?: string[];
  models_detail?: string | null;
};

type EndpointHealth = "ok" | "unreachable" | "no_model";

function endpointHealth(ep: EndpointRow): EndpointHealth {
  const models = (ep.models ?? []).filter((m) => m.trim());
  const hasModel = Boolean((ep.model_default || "").trim());
  if (models.length === 0) return "unreachable";
  if (!hasModel) return "no_model";
  return "ok";
}

type EnvPreview = {
  index: number;
  label: string;
  base_url: string;
  already_in_db?: boolean;
  model_default?: string | null;
  api_header_name?: string;
};

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

type Props = {
  kind: ProviderEndpointKind;
  accessToken: string;
  /** When true, cards can mark primary among multiple endpoints (chat only). */
  allowPrimary?: boolean;
  defaultName?: string;
  onChanged?: () => void;
};

export function SetupProviderEndpointsPanel({
  kind,
  accessToken,
  allowPrimary = false,
  defaultName = "",
  onChanged,
}: Props) {
  const { t } = useTranslation(["setup"]);
  const [endpoints, setEndpoints] = useState<EndpointRow[]>([]);
  const [envProviders, setEnvProviders] = useState<EnvPreview[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [importPending, setImportPending] = useState(false);
  const [deletePendingId, setDeletePendingId] = useState<number | null>(null);
  const [primaryPendingId, setPrimaryPendingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const [preset, setPreset] = useState<LlmPresetId>(DEFAULT_LLM_PRESET);
  const [name, setName] = useState(defaultName);
  const [baseUrl, setBaseUrl] = useState(getPresetForKind(kind, DEFAULT_LLM_PRESET).baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [apiHeaderName, setApiHeaderName] = useState("Authorization");
  const [model, setModel] = useState("");
  const [probedModels, setProbedModels] = useState<string[]>([]);
  const bootstrappedKind = useRef<string | null>(null);

  const presetConfig = getPresetForKind(kind, preset);
  const presets = listPresetsForKind(kind);
  const envToImport = envProviders.filter((p) => !p.already_in_db);

  const reload = useCallback(async (): Promise<{
    endpoints: EndpointRow[];
    envProviders: EnvPreview[];
  }> => {
    setLoading(true);
    setError(null);
    let nextEndpoints: EndpointRow[] = [];
    let nextEnv: EnvPreview[] = [];
    try {
      const [listR, envR] = await Promise.all([
        fetch(`/v1/admin/provider-endpoints/${kind}`, {
          credentials: "include",
          headers: authHeaders(accessToken),
        }),
        fetch(`/v1/admin/provider-endpoints/${kind}/env-providers`, {
          credentials: "include",
          headers: authHeaders(accessToken),
        }),
      ]);
      if (!listR.ok) {
        setError(t("setup:requestFailed"));
        setLoading(false);
        return { endpoints: [], envProviders: [] };
      }
      const listData = (await listR.json()) as { endpoints?: EndpointRow[] };
      nextEndpoints = listData.endpoints ?? [];
      setEndpoints(nextEndpoints);
      if (envR.ok) {
        const envData = (await envR.json()) as { providers?: EnvPreview[] };
        nextEnv = envData.providers ?? [];
        setEnvProviders(nextEnv);
      } else {
        setEnvProviders([]);
      }
    } catch {
      setError(t("setup:requestFailed"));
    }
    setLoading(false);
    return { endpoints: nextEndpoints, envProviders: nextEnv };
  }, [accessToken, kind, t]);

  function seedFormFromEnv(envList: EnvPreview[]) {
    const seed = envList.find((p) => !p.already_in_db) || envList[0];
    if (!seed?.base_url?.trim()) return;
    setPreset("provider_1");
    setName(seed.label || defaultName || getPresetForKind(kind, "provider_1").endpointLabel);
    setBaseUrl(seed.base_url.trim());
    setApiHeaderName(seed.api_header_name || "Authorization");
    const md = (seed.model_default || "").trim();
    if (md) {
      setProbedModels([md]);
      setModel(md);
    }
  }

  async function importEnvProviders(): Promise<boolean> {
    setImportPending(true);
    setError(null);
    const r = await fetch(`/v1/admin/provider-endpoints/${kind}/env-providers/import`, {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({}),
    });
    setImportPending(false);
    if (!r.ok) {
      let msg = t("setup:importEnvFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setError(msg);
      return false;
    }
    return true;
  }

  async function fillMissingModels(rows: EndpointRow[]) {
    let changed = false;
    for (const ep of rows) {
      const current = (ep.model_default || "").trim();
      const models = (ep.models ?? []).filter((m) => m.trim());
      if (!models.length || !ep.base_url.trim()) continue;
      // Only auto-fill when empty. Never replace a user/env pick.
      // Also clear a bogus chat default on embedding cards (gateway kinds=embed leak).
      const bogusEmbeddingDefault =
        kind === "embedding" && current && !models.includes(current);
      if (current && !bogusEmbeddingDefault) continue;
      const pick = models[0];
      if (!pick) continue;
      const r = await fetch(`/v1/admin/provider-endpoints/${kind}/upsert`, {
        method: "POST",
        credentials: "include",
        headers: authHeaders(accessToken),
        body: JSON.stringify({
          label: ep.label || defaultName || kind,
          base_url: ep.base_url.trim(),
          api_key: null,
          api_header_name: ep.api_header_name || "Authorization",
          model_default: pick,
          max_parallel: 1,
          options_json: {},
          enabled: true,
        }),
      });
      if (r.ok) changed = true;
    }
    return changed;
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const first = await reload();
      if (cancelled) return;

      // Same for every kind: import env once ONLY when DB is empty.
      // Never re-import on Back/remount — that used to recreate host vs /v1 twins
      // and overwrite defaults with ranked/env models the user never picked.
      if (bootstrappedKind.current !== kind) {
        bootstrappedKind.current = kind;
        const pendingEnv = first.envProviders.filter((p) => !p.already_in_db);
        if (first.endpoints.length === 0 && pendingEnv.length > 0) {
          const ok = await importEnvProviders();
          if (cancelled) return;
          if (ok) {
            let after = await reload();
            if (cancelled) return;
            if (await fillMissingModels(after.endpoints)) {
              if (cancelled) return;
              after = await reload();
            }
            onChanged?.();
            const bad = after.endpoints.filter((ep) => endpointHealth(ep) !== "ok").length;
            setOkMsg(
              bad > 0
                ? t("setup:envAutoImportedWithIssues", { count: pendingEnv.length, bad })
                : t("setup:envAutoImported", { count: pendingEnv.length })
            );
            return;
          }
        }
        if (first.endpoints.length === 0 && !baseUrl.trim() && first.envProviders.length > 0) {
          seedFormFromEnv(first.envProviders);
        }
        if (await fillMissingModels(first.endpoints)) {
          if (cancelled) return;
          await reload();
          onChanged?.();
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Bootstrap once per kind mount; reload identity is stable enough via kind/token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, accessToken]);

  useEffect(() => {
    if (defaultName && !name.trim()) setName(defaultName);
  }, [defaultName, name]);

  function clearProbe() {
    setProbedModels([]);
    setModel("");
    setOkMsg(null);
  }

  function onEdit(ep: EndpointRow) {
    setEditingId(ep.id);
    setName(ep.label || defaultName);
    setBaseUrl(ep.base_url || "");
    setApiKey("");
    setPreset("custom");
    const md = (ep.model_default || "").trim();
    if (md) {
      setProbedModels([md]);
      setModel(md);
    } else {
      clearProbe();
    }
    setOkMsg(t("setup:endpointEditHint"));
    setError(null);
  }

  function sortedEndpoints(): EndpointRow[] {
    return [...endpoints].sort(
      (a, b) => (a.sort_order ?? a.id) - (b.sort_order ?? b.id) || a.id - b.id
    );
  }

  async function onProbe() {
    if (!baseUrl.trim()) {
      setError(t("setup:llmBaseUrlRequired"));
      return;
    }
    if (presetConfig.apiKeyRequired && !apiKey.trim()) {
      setError(t("setup:llmApiKeyRequired", { label: presetConfig.endpointLabel }));
      return;
    }
    setPending(true);
    setError(null);
    setOkMsg(null);
    const r = await fetch(`/v1/admin/provider-endpoints/${kind}/probe`, {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || null,
      }),
    });
    setPending(false);
    if (!r.ok) {
      let msg = t("setup:requestFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setError(msg);
      return;
    }
    const d = (await r.json()) as { model_count?: number; models?: string[] };
    const models = (d.models ?? []).filter((m) => typeof m === "string" && m.trim());
    if (models.length === 0) {
      setProbedModels([]);
      setModel("");
      setError(t("setup:llmTestNoModels"));
      return;
    }
    setProbedModels(models);
    setModel((prev) => (prev && models.includes(prev) ? prev : models[0] || ""));
    setOkMsg(t("setup:llmTestOkCount", { count: d.model_count ?? models.length }));
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    const label = name.trim();
    if (!label) {
      setError(t("setup:endpointNameRequired"));
      return;
    }
    if (!baseUrl.trim()) {
      setError(t("setup:llmBaseUrlRequired"));
      return;
    }
    if (probedModels.length === 0) {
      setError(t("setup:llmTestBeforeSave"));
      return;
    }
    if (!model.trim() || !probedModels.includes(model.trim())) {
      setError(t("setup:llmPickModelFromList"));
      return;
    }
    setPending(true);
    setError(null);
    const r = await fetch(`/v1/admin/provider-endpoints/${kind}/upsert`, {
      method: "POST",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        label,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || null,
        api_header_name: apiHeaderName || "Authorization",
        model_default: model.trim(),
        max_parallel: 1,
        options_json: {},
        enabled: true,
      }),
    });
    setPending(false);
    if (!r.ok) {
      let msg = t("setup:requestFailed");
      try {
        const d = (await r.json()) as { detail?: string };
        if (typeof d.detail === "string") msg = d.detail;
      } catch {
        /* ignore */
      }
      setError(msg);
      return;
    }
    setApiKey("");
    setEditingId(null);
    clearProbe();
    setOkMsg(t("setup:endpointSaved"));
    await reload();
    onChanged?.();
  }

  async function onMakePrimary(id: number) {
    setPrimaryPendingId(id);
    setError(null);
    const ordered = sortedEndpoints();
    const primary = ordered.find((ep) => ep.id === id);
    if (!primary) {
      setPrimaryPendingId(null);
      return;
    }
    const rest = ordered.filter((ep) => ep.id !== id);
    const next = [primary, ...rest].map((ep, i) => ({
      id: ep.id,
      sort_order: i,
      enabled: true,
      label: ep.label,
      base_url: ep.base_url,
      api_key: null,
      api_header_name: ep.api_header_name || "Authorization",
      model_default: ep.model_default ?? null,
      max_parallel: 1,
      options_json: {},
    }));
    const r = await fetch(`/v1/admin/provider-endpoints/${kind}`, {
      method: "PUT",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({ endpoints: next, delete_endpoint_ids: [] }),
    });
    setPrimaryPendingId(null);
    if (!r.ok) {
      setError(t("setup:endpointPrimaryFailed"));
      return;
    }
    await reload();
    onChanged?.();
  }

  async function onImportEnv() {
    const ok = await importEnvProviders();
    if (!ok) return;
    const after = await reload();
    if (await fillMissingModels(after.endpoints)) {
      await reload();
    }
    onChanged?.();
    setOkMsg(t("setup:envAutoImported", { count: envToImport.length || 1 }));
  }

  async function onDelete(id: number) {
    setDeletePendingId(id);
    setError(null);
    const r = await fetch(`/v1/admin/provider-endpoints/${kind}`, {
      method: "PUT",
      credentials: "include",
      headers: authHeaders(accessToken),
      body: JSON.stringify({
        endpoints: endpoints
          .filter((ep) => ep.id !== id)
          .map((ep, i) => ({
            id: ep.id,
            sort_order: i,
            enabled: true,
            label: ep.label,
            base_url: ep.base_url,
            api_key: null,
            api_header_name: ep.api_header_name || "Authorization",
            model_default: ep.model_default ?? null,
            max_parallel: 1,
            options_json: {},
          })),
        delete_endpoint_ids: [id],
      }),
    });
    setDeletePendingId(null);
    if (!r.ok) {
      setError(t("setup:endpointDeleteFailed"));
      return;
    }
    await reload();
    onChanged?.();
  }

  return (
    <div className="space-y-wide">
      <section>
        <h2 className="text-sm font-medium text-ink-primary">{t("setup:providerStatus")}</h2>
        {loading ? (
          <p className="mt-base text-sm text-ink-muted">{t("setup:catalogLoading")}</p>
        ) : null}
        <ul className="mt-base space-y-base">
          {sortedEndpoints().map((ep, index) => {
            const isPrimary = allowPrimary && index === 0;
            const health = endpointHealth(ep);
            const statusClass =
              health === "ok" ? "text-success" : health === "no_model" ? "text-warning" : "text-danger";
            const statusLabel =
              health === "ok"
                ? t("setup:reachable")
                : health === "no_model"
                  ? t("setup:cardStatusNoModel")
                  : t("setup:notReachable");
            return (
              <li
                key={ep.id}
                className={`rounded-card border px-soft py-base text-sm ${
                  editingId === ep.id
                    ? "border-accent bg-card"
                    : health === "ok"
                      ? "border-line bg-card"
                      : "border-badge-warning/40 bg-card"
                }`}
              >
                <div className="flex items-start justify-between gap-base">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-soft">
                      <span className="font-medium text-ink-primary">{ep.label}</span>
                      {isPrimary ? (
                        <span className="text-xs text-badge-accent">{t("setup:primaryBadge")}</span>
                      ) : null}
                      <span className={`text-xs font-medium ${statusClass}`}>{statusLabel}</span>
                    </div>
                    <p className="mt-tight text-xs text-ink-muted break-all">{ep.base_url}</p>
                    <p className="mt-tight text-xs text-ink-muted">
                      {t("setup:cardDefaultModel")}:{" "}
                      <span className={ep.model_default?.trim() ? "text-ink-primary" : "text-warning"}>
                        {ep.model_default?.trim() || t("setup:cardDefaultModelNone")}
                      </span>
                    </p>
                    {health === "unreachable" ? (
                      <p className="mt-tight text-xs text-danger" role="status">
                        {ep.models_detail?.trim() || t("setup:cardUnreachableHint")}
                      </p>
                    ) : null}
                    {health !== "unreachable" && ep.models_detail?.trim() ? (
                      <p className="mt-tight text-xs text-warning" role="status">
                        {ep.models_detail.trim()}
                      </p>
                    ) : null}
                    {health === "no_model" ? (
                      <p className="mt-tight text-xs text-warning" role="status">
                        {t("setup:cardNoModelHint")}
                      </p>
                    ) : null}
                    {health === "ok" && (ep.models?.length ?? 0) > 0 ? (
                      <p className="mt-tight text-xs text-ink-muted">
                        {t("setup:cardModelsAvailable", { count: ep.models!.length })}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-wrap justify-end gap-tight">
                    <Button
                      type="button"
                      className="px-soft py-tight text-xs hover:bg-white/5"
                      disabled={loading || pending}
                      onClick={() => void reload()}
                    >
                      {t("setup:retryCheck")}
                    </Button>
                    <Button
                      type="button"
                      className="px-soft py-tight text-xs hover:bg-white/5"
                      onClick={() => onEdit(ep)}
                    >
                      {t("setup:editEndpoint")}
                    </Button>
                    {allowPrimary && endpoints.length > 1 && !isPrimary ? (
                      <Button
                        type="button"
                        className="px-soft py-tight text-xs hover:bg-white/5"
                        disabled={primaryPendingId === ep.id}
                        onClick={() => void onMakePrimary(ep.id)}
                      >
                        {t("setup:makePrimary")}
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      className="px-soft py-tight text-xs hover:bg-white/5"
                      disabled={deletePendingId === ep.id}
                      onClick={() => void onDelete(ep.id)}
                    >
                      {t("setup:deleteEndpoint")}
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
          {!loading && endpoints.length === 0 ? (
            <li className="text-sm text-ink-muted">{t("setup:noProvidersYet")}</li>
          ) : null}
        </ul>
        {!loading && endpoints.some((ep) => endpointHealth(ep) !== "ok") ? (
          <p className="mt-soft text-xs text-warning" role="status">
            {t("setup:endpointHealthFooter")}
          </p>
        ) : null}
        {envToImport.length > 0 ? (
          <Button
            type="button"
            className="mt-soft px-soft py-base text-sm hover:bg-white/5"
            disabled={importPending}
            onClick={() => void onImportEnv()}
          >
            {importPending
              ? t("setup:importEnvPending")
              : t("setup:importEnvKind", { count: envToImport.length })}
          </Button>
        ) : null}
      </section>

      <form
        onSubmit={(e) => void onSave(e)}
        className="flex flex-col gap-wide rounded-card border border-line bg-card px-soft py-wide"
      >
        <h2 className="text-sm font-medium text-ink-primary">
          {editingId != null ? t("setup:editEndpointTitle") : t("setup:addEndpointTitle")}
        </h2>
        <label className="flex flex-col gap-snug text-sm">
          <span className="text-ink-muted">{t("setup:endpointName")}</span>
          <TextInput
            type="text"
            value={name}
            onChange={(ev) => setName(ev.target.value)}
            required
            maxLength={512}
          />
        </label>
        <label className="flex flex-col gap-snug text-sm">
          <span className="text-ink-muted">{t("setup:preset")}</span>
          <Select
            value={preset}
            onChange={(ev) => {
              const p = ev.target.value as LlmPresetId;
              const cfg = getPresetForKind(kind, p);
              setPreset(p);
              clearProbe();
              if (p === "provider_1" && envProviders.length > 0) {
                seedFormFromEnv(envProviders);
                return;
              }
              if (p !== "custom") {
                setBaseUrl(cfg.baseUrl);
                if (!name.trim() || name === presetConfig.endpointLabel || name === defaultName) {
                  setName(cfg.endpointLabel);
                }
              }
            }}
          >
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {t(`setup:${p.labelKey}`)}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-snug text-sm">
          <span className="text-ink-muted">{t("setup:baseUrl")}</span>
          <TextInput
            type="url"
            value={baseUrl}
            onChange={(ev) => {
              setBaseUrl(ev.target.value);
              setPreset("custom");
              clearProbe();
            }}
            required
          />
        </label>
        <label className="flex flex-col gap-snug text-sm">
          <span className="text-ink-muted">
            {t("setup:apiKey")}
            {presetConfig.apiKeyRequired ? t("setup:apiKeyRequired") : t("setup:apiKeyOptional")}
          </span>
          <TextInput
            type="password"
            value={apiKey}
            onChange={(ev) => {
              setApiKey(ev.target.value);
              clearProbe();
            }}
            autoComplete="off"
            required={presetConfig.apiKeyRequired}
          />
        </label>
        <label className="flex flex-col gap-snug text-sm">
          <span className="text-ink-muted">{t("setup:defaultModel")}</span>
          <Select
            value={model}
            onChange={(ev) => setModel(ev.target.value)}
            disabled={probedModels.length === 0}
          >
            {probedModels.length === 0 ? (
              <option value="">{t("setup:defaultModelTestFirst")}</option>
            ) : (
              probedModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))
            )}
          </Select>
        </label>
        {error ? (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}
        {okMsg ? (
          <p className="text-sm text-success" role="status">
            {okMsg}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-soft">
          <Button
            type="button"
            disabled={pending}
            onClick={() => void onProbe()}
            className="px-wide py-firm text-sm hover:bg-white/5"
          >
            {t("setup:testConnection")}
          </Button>
          <Button
            type="submit"
            disabled={pending || probedModels.length === 0 || !model}
            className="px-wide py-firm text-sm hover:bg-white/5"
          >
            {t("setup:saveEndpoint")}
          </Button>
          <Button
            type="button"
            disabled={loading}
            onClick={() => void reload()}
            className="px-wide py-firm text-sm hover:bg-white/5"
          >
            {t("setup:refresh")}
          </Button>
        </div>
      </form>
    </div>
  );
}
