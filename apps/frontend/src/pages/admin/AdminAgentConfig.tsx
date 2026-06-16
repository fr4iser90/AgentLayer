import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  applyAgentConfigModelPatches,
  applyAgentConfigPatches,
  deleteAgentConfigModelOverride,
  fetchAgentConfigChangelog,
  fetchAgentConfigFingerprint,
  fetchAgentConfigKnobs,
  fetchAgentConfigModelOverrides,
  type AgentConfigKnob,
  type AgentConfigModelOverride,
  isHarnessKnob,
} from "../../features/admin/agentConfig/agentConfigApi";
import { fetchBenchmarkLlmProviders, type BenchmarkLlmProvider } from "../../features/admin/benchmarks/benchmarksApi";

type Tab = "knobs" | "models";

function knobHelpKey(id: string) {
  return `harnessKnobHelp_${id.replace(/\./g, "_")}`;
}

export function AdminAgentConfig() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();

  const formatKnobValue = (knob: AgentConfigKnob): string => {
    const v = knob.effective;
    if (v === null || v === undefined) {
      if (knob.effective_label) return knob.effective_label;
      if (knob.id === "tool_routing.domain_order") return t("admin:agentConfigDomainOrderEmpty");
      return "—";
    }
    if (typeof v === "boolean") return v ? "true" : "false";
    if (Array.isArray(v)) {
      return v.length ? v.join(", ") : t("admin:agentConfigDomainOrderEmpty");
    }
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  };

  const formatKnobSource = (source: string | undefined): string => {
    if (!source) return "—";
    const key = `agentConfigSource_${source}`;
    const translated = t(`admin:${key}`, { defaultValue: "" });
    return translated || source;
  };

  const [knobs, setKnobs] = useState<AgentConfigKnob[]>([]);
  const [fingerprint, setFingerprint] = useState<string>("");
  const [gitSha, setGitSha] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [editValue, setEditValue] = useState<string>("");
  const [hypothesis, setHypothesis] = useState("");
  const [events, setEvents] = useState<unknown[]>([]);
  const [applyBusy, setApplyBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("knobs");

  const [providers, setProviders] = useState<BenchmarkLlmProvider[]>([]);
  const [modelOverrides, setModelOverrides] = useState<AgentConfigModelOverride[]>([]);
  const [modelScopeCatalog, setModelScopeCatalog] = useState("");
  const [modelScopeModel, setModelScopeModel] = useState("");
  const [modelScopeLabel, setModelScopeLabel] = useState("");
  const [modelScopeOverrideId, setModelScopeOverrideId] = useState<string | null>(null);

  const benchProviders = useMemo(
    () => providers.filter((p) => Boolean(p.catalog_owned_by?.trim())),
    [providers],
  );

  const reloadGlobal = useCallback(async () => {
    const [k, fp, cl] = await Promise.all([
      fetchAgentConfigKnobs(auth),
      fetchAgentConfigFingerprint(auth),
      fetchAgentConfigChangelog(auth),
    ]);
    setKnobs((k.knobs || []).filter(isHarnessKnob));
    setFingerprint(String(fp.fingerprint || ""));
    setGitSha(String(fp.git_sha || ""));
    setEvents(cl.events || []);
  }, [auth]);

  const reloadModelKnobs = useCallback(
    async (catalog: string, model: string) => {
      if (!catalog.trim()) {
        setKnobs([]);
        return;
      }
      const k = await fetchAgentConfigKnobs(auth, {
        catalog_owned_by: catalog.trim(),
        model: model.trim() || undefined,
      });
      setKnobs((k.knobs || []).filter(isHarnessKnob));
    },
    [auth],
  );

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [llm, overrides, fp] = await Promise.all([
        fetchBenchmarkLlmProviders(auth),
        fetchAgentConfigModelOverrides(auth),
        fetchAgentConfigFingerprint(auth),
      ]);
      setProviders(llm);
      setModelOverrides(overrides.overrides || []);
      setFingerprint(String(fp.fingerprint || ""));
      setGitSha(String(fp.git_sha || ""));
      if (tab === "models") {
        await reloadModelKnobs(modelScopeCatalog, modelScopeModel);
      } else {
        await reloadGlobal();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, tab, modelScopeCatalog, modelScopeModel, reloadGlobal, reloadModelKnobs]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (tab !== "models") return;
    void reloadModelKnobs(modelScopeCatalog, modelScopeModel).catch((e) => {
      setError(e instanceof Error ? e.message : String(e));
    });
  }, [tab, modelScopeCatalog, modelScopeModel, reloadModelKnobs]);

  const selected = knobs.find((k) => k.id === selectedId);

  useEffect(() => {
    if (!selected) {
      setEditValue("");
      return;
    }
    const v = selected.effective ?? selected.default ?? "";
    setEditValue(typeof v === "string" ? v : JSON.stringify(v));
  }, [selected]);

  function selectModelOverride(row: AgentConfigModelOverride | null) {
    if (!row) {
      setModelScopeOverrideId(null);
      setModelScopeCatalog(benchProviders[0]?.catalog_owned_by || "");
      setModelScopeModel("");
      setModelScopeLabel("");
      return;
    }
    setModelScopeOverrideId(row.id);
    setModelScopeCatalog(row.catalog_owned_by);
    setModelScopeModel(row.model || "");
    setModelScopeLabel(row.label || "");
  }

  async function onApply() {
    if (!auth.accessToken || !selectedId || selected?.writable === false) return;
    setApplyBusy(true);
    setError(null);
    try {
      let value: unknown = editValue;
      if (selected?.type === "integer") value = parseInt(editValue, 10);
      else if (selected?.type === "boolean") value = editValue === "true";
      else if (selected?.type === "string_list") value = JSON.parse(editValue || "[]");
      if (tab === "models") {
        if (!modelScopeCatalog.trim()) {
          setError(t("admin:agentConfigModelsProviderRequired"));
          return;
        }
        await applyAgentConfigModelPatches(auth, {
          catalog_owned_by: modelScopeCatalog.trim(),
          model: modelScopeModel.trim() || null,
          label: modelScopeLabel.trim() || null,
          override_id: modelScopeOverrideId,
          patches: [{ knob_id: selectedId, value }],
          hypothesis: hypothesis.trim() || undefined,
        });
      } else {
        await applyAgentConfigPatches(auth, {
          patches: [{ knob_id: selectedId, value }],
          hypothesis: hypothesis.trim() || undefined,
        });
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplyBusy(false);
    }
  }

  async function onDeleteModelOverride() {
    if (!modelScopeOverrideId) return;
    if (!window.confirm(t("admin:agentConfigModelsDeleteConfirm"))) return;
    setApplyBusy(true);
    setError(null);
    try {
      await deleteAgentConfigModelOverride(auth, modelScopeOverrideId);
      selectModelOverride(null);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplyBusy(false);
    }
  }

  const knobEditor = (
    <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-2">
      <section className="min-h-0 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
        <h2 className="mb-2 text-sm font-medium text-white">{t("admin:agentConfigKnobs")}</h2>
        <ul className="space-y-1">
          {knobs.map((k) => (
            <li key={k.id}>
              <button
                type="button"
                onClick={() => setSelectedId(k.id)}
                className={`w-full rounded px-2 py-1.5 text-left text-sm ${
                  selectedId === k.id ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5"
                }`}
              >
                <span className="font-mono text-xs">{k.id}</span>
                {k.writable === false ? (
                  <span className="ml-2 text-[10px] uppercase text-amber-400/80">
                    {t("admin:agentConfigKnobsReadOnly")}
                  </span>
                ) : null}
                <span className="ml-2 text-xs opacity-70">{formatKnobValue(k)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex min-h-0 flex-col gap-3 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
        <h2 className="text-sm font-medium text-white">{t("admin:agentConfigApply")}</h2>
        {selected ? (
          <>
            <p className="text-xs text-surface-muted">
              {selected.layer ? `[${selected.layer}] ` : ""}
              {selected.doc}
            </p>
            <div className="rounded border border-surface-border/60 bg-black/20 p-2 text-xs text-surface-muted">
              <p className="font-medium text-white/90">{t("admin:agentConfigEffectiveNow")}</p>
              <p className="mt-1 font-mono">{formatKnobValue(selected)}</p>
              <p className="mt-2">
                {t("admin:agentConfigEffectiveSource")}: {formatKnobSource(selected.source)}
              </p>
              {selected.default !== undefined && selected.default !== null ? (
                <p className="mt-1">
                  Registry default:{" "}
                  <span className="font-mono">
                    {typeof selected.default === "object"
                      ? JSON.stringify(selected.default)
                      : String(selected.default)}
                  </span>
                </p>
              ) : null}
            </div>
            <div className="rounded border border-blue-500/30 bg-blue-500/5 p-2 text-xs text-blue-100/90">
              {t(`admin:${knobHelpKey(selected.id)}`, {
                defaultValue: selected.doc || selected.id,
              })}
            </div>
            {selected.writable === false ? (
              <p className="text-xs text-amber-300/90">{t("admin:agentConfigKnobsReadOnly")}</p>
            ) : null}
            <label className="text-xs text-surface-muted">{t("admin:agentConfigValue")}</label>
            <textarea
              className="min-h-[80px] w-full rounded border border-surface-border bg-black/30 p-2 font-mono text-sm text-white disabled:opacity-50"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              disabled={selected.writable === false}
            />
            <label className="text-xs text-surface-muted">{t("admin:agentConfigHypothesis")}</label>
            <p className="text-[11px] text-surface-muted/80">{t("admin:agentConfigHypothesisHint")}</p>
            <input
              className="w-full rounded border border-surface-border bg-black/30 p-2 text-sm text-white disabled:opacity-50"
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
              disabled={selected.writable === false}
            />
            <button
              type="button"
              disabled={applyBusy || selected.writable === false}
              onClick={() => void onApply()}
              className="rounded bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              {applyBusy ? t("admin:agentConfigApplying") : t("admin:agentConfigApplyBtn")}
            </button>
          </>
        ) : (
          <p className="text-sm text-surface-muted">{t("admin:agentConfigSelectKnob")}</p>
        )}

        {tab === "knobs" ? (
          <>
            <h3 className="mt-4 text-sm font-medium text-white">{t("admin:agentConfigChangelog")}</h3>
            <ul className="space-y-2 text-xs text-surface-muted">
              {(events as { id?: string; at?: string; patches?: unknown[] }[]).slice(0, 10).map((ev) => (
                <li key={ev.id} className="rounded border border-surface-border/60 p-2">
                  <div>{ev.at}</div>
                  <pre className="mt-1 overflow-auto whitespace-pre-wrap">{JSON.stringify(ev.patches, null, 2)}</pre>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden p-4 md:p-6">
      <header className="mb-4 shrink-0">
        <h1 className="text-lg font-semibold text-white">{t("admin:agentConfigTitle")}</h1>
        <p className="mt-1 text-sm text-surface-muted">{t("admin:agentConfigSubtitle")}</p>
        {fingerprint ? (
          <p className="mt-2 font-mono text-xs text-surface-muted break-all">{fingerprint}</p>
        ) : null}
        {gitSha ? (
          <p className="mt-1 font-mono text-xs text-surface-muted">
            {t("admin:agentConfigGitSha")}: {gitSha}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {(["knobs", "models"] as Tab[]).map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded px-3 py-1 text-xs ${
                tab === id ? "bg-white/15 text-white" : "text-surface-muted hover:bg-white/5"
              }`}
            >
              {t(`admin:agentConfigTab_${id}`)}
            </button>
          ))}
        </div>
      </header>

      {error ? (
        <p className="mb-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
      ) : tab === "models" ? (
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <p className="text-xs text-surface-muted">{t("admin:agentConfigModelsHint")}</p>
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[240px_1fr]">
            <section className="min-h-0 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-sm font-medium text-white">{t("admin:agentConfigModelsList")}</h2>
                <button
                  type="button"
                  className="text-xs text-sky-400 hover:underline"
                  onClick={() => selectModelOverride(null)}
                >
                  {t("admin:agentConfigModelsNew")}
                </button>
              </div>
              <ul className="space-y-1 text-sm">
                {modelOverrides.map((row) => {
                  const active = modelScopeOverrideId === row.id;
                  const modelLabel = row.model?.trim() || t("admin:agentConfigModelsModelHint");
                  return (
                    <li key={row.id}>
                      <button
                        type="button"
                        onClick={() => selectModelOverride(row)}
                        className={`w-full rounded px-2 py-1.5 text-left ${
                          active ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5"
                        }`}
                      >
                        <div className="font-mono text-[11px]">{row.catalog_owned_by}</div>
                        <div className="truncate text-xs opacity-80">{modelLabel}</div>
                        {row.label ? <div className="text-[10px] opacity-60">{row.label}</div> : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>

            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <section className="shrink-0 rounded-lg border border-surface-border bg-[#111] p-3">
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="block text-sm">
                    <span className="text-xs text-surface-muted">{t("admin:agentConfigModelsProvider")}</span>
                    <select
                      value={modelScopeCatalog}
                      onChange={(e) => {
                        setModelScopeOverrideId(null);
                        setModelScopeCatalog(e.target.value);
                      }}
                      className="mt-1 w-full rounded border border-surface-border bg-black/30 px-2 py-1.5 text-sm text-white"
                    >
                      <option value="">—</option>
                      {benchProviders.map((p) => (
                        <option key={p.catalog_owned_by} value={p.catalog_owned_by}>
                          {p.label} ({p.catalog_owned_by})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="text-xs text-surface-muted">{t("admin:agentConfigModelsModel")}</span>
                    <input
                      value={modelScopeModel}
                      onChange={(e) => {
                        setModelScopeOverrideId(null);
                        setModelScopeModel(e.target.value);
                      }}
                      placeholder={t("admin:agentConfigModelsModelHint")}
                      className="mt-1 w-full rounded border border-surface-border bg-black/30 px-2 py-1.5 font-mono text-sm text-white"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-xs text-surface-muted">{t("admin:agentConfigModelsLabel")}</span>
                    <input
                      value={modelScopeLabel}
                      onChange={(e) => setModelScopeLabel(e.target.value)}
                      className="mt-1 w-full rounded border border-surface-border bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                </div>
                {modelScopeOverrideId ? (
                  <button
                    type="button"
                    disabled={applyBusy}
                    onClick={() => void onDeleteModelOverride()}
                    className="mt-3 rounded border border-red-500/40 px-3 py-1 text-xs text-red-200 hover:bg-red-500/10 disabled:opacity-50"
                  >
                    {t("admin:agentConfigModelsDelete")}
                  </button>
                ) : null}
              </section>

              {modelScopeCatalog.trim() ? knobEditor : (
                <p className="text-sm text-surface-muted">{t("admin:agentConfigModelsSelect")}</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        knobEditor
      )}
    </div>
  );
}
