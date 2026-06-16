import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { fetchBenchmarkLlmProviders, type BenchmarkLlmProvider } from "../../features/admin/benchmarks/benchmarksApi";
import {
  createHarnessOverride,
  deleteHarnessOverride,
  fetchHarnessMatrix,
  saveHarnessGlobal,
  updateHarnessOverride,
  type HarnessConfigFields,
  type HarnessModelOverride,
  type HarnessPreset,
} from "../../features/admin/harness/harnessApi";

const emptyOverrideForm = (): HarnessConfigFields & {
  catalog_owned_by: string;
  model: string;
  label: string;
} => ({
  catalog_owned_by: "",
  model: "",
  label: "",
  harness_preset: "observability",
  max_tool_rounds_override: null,
  scenario_timeout_sec: null,
  capture_timeline: null,
  stream_llm: null,
  notes: "",
});

function parseOptionalInt(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? Math.floor(n) : null;
}

function parseOptionalFloat(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function AdminHarnessConfig() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<BenchmarkLlmProvider[]>([]);
  const [overrides, setOverrides] = useState<HarnessModelOverride[]>([]);

  const [globalPreset, setGlobalPreset] = useState<HarnessPreset>("observability");
  const [globalMaxRounds, setGlobalMaxRounds] = useState("");
  const [globalTimeout, setGlobalTimeout] = useState("");
  const [globalNotes, setGlobalNotes] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [overrideForm, setOverrideForm] = useState(emptyOverrideForm);

  const benchProviders = useMemo(
    () => providers.filter((p) => Boolean(p.base_url?.trim())),
    [providers]
  );

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [matrix, llm] = await Promise.all([
        fetchHarnessMatrix(auth),
        fetchBenchmarkLlmProviders(auth),
      ]);
      setProviders(llm);
      setOverrides(matrix.overrides || []);
      const g = matrix.global;
      setGlobalPreset((g.harness_preset as HarnessPreset) || "observability");
      setGlobalMaxRounds(
        g.max_tool_rounds_override != null ? String(g.max_tool_rounds_override) : ""
      );
      setGlobalTimeout(g.scenario_timeout_sec != null ? String(g.scenario_timeout_sec) : "");
      setGlobalNotes(g.notes || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const globalBody = (): HarnessConfigFields => ({
    harness_preset: globalPreset,
    max_tool_rounds_override: parseOptionalInt(globalMaxRounds),
    scenario_timeout_sec: parseOptionalFloat(globalTimeout),
    notes: globalNotes.trim() || null,
  });

  async function onSaveGlobal() {
    setBusy(true);
    setError(null);
    try {
      await saveHarnessGlobal(auth, globalBody());
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(row: HarnessModelOverride) {
    setEditingId(row.id);
    setOverrideForm({
      catalog_owned_by: row.catalog_owned_by,
      model: row.model || "",
      label: row.label || "",
      harness_preset: (row.harness_preset as HarnessPreset) || "observability",
      max_tool_rounds_override: row.max_tool_rounds_override ?? null,
      scenario_timeout_sec: row.scenario_timeout_sec ?? null,
      capture_timeline: row.capture_timeline ?? null,
      stream_llm: row.stream_llm ?? null,
      notes: row.notes || "",
    });
  }

  function resetOverrideForm() {
    setEditingId(null);
    setOverrideForm(emptyOverrideForm());
  }

  async function onSaveOverride() {
    if (!overrideForm.catalog_owned_by.trim()) {
      setError(t("admin:harnessOverrideProviderRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = {
        catalog_owned_by: overrideForm.catalog_owned_by.trim(),
        model: overrideForm.model.trim() || null,
        label: overrideForm.label.trim() || null,
        harness_preset: overrideForm.harness_preset,
        max_tool_rounds_override: overrideForm.max_tool_rounds_override,
        scenario_timeout_sec: overrideForm.scenario_timeout_sec,
        capture_timeline: overrideForm.capture_timeline,
        stream_llm: overrideForm.stream_llm,
        notes: overrideForm.notes?.trim() || null,
      };
      if (editingId) {
        await updateHarnessOverride(auth, editingId, body);
      } else {
        await createHarnessOverride(auth, body);
      }
      resetOverrideForm();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteOverride(id: string) {
    if (!window.confirm(t("admin:harnessDeleteOverrideConfirm"))) return;
    setBusy(true);
    setError(null);
    try {
      await deleteHarnessOverride(auth, id);
      if (editingId === id) resetOverrideForm();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-white/10 px-4 py-3">
        <h1 className="text-lg font-semibold text-white">{t("admin:harnessTitle")}</h1>
        <p className="mt-1 text-sm text-surface-muted">{t("admin:harnessSubtitle")}</p>
        <p className="mt-2 text-xs text-surface-muted">
          {t("admin:harnessWorkflowHint")}{" "}
          <Link to="/admin/benchmarks" className="text-sky-400 hover:underline">
            {t("admin:benchNav")}
          </Link>
          {" · "}
          <Link to="/admin/agent-config" className="text-sky-400 hover:underline">
            {t("admin:agentConfigNav")}
          </Link>
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {error ? (
          <p className="mb-4 rounded border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
            {error}
          </p>
        ) : null}
        {loading ? (
          <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
        ) : (
          <div className="mx-auto max-w-5xl space-y-8">
            <section className="rounded-lg border border-white/10 bg-black/20 p-4">
              <h2 className="text-sm font-medium text-white">{t("admin:harnessGlobalTitle")}</h2>
              <p className="mt-1 text-xs text-surface-muted">{t("admin:harnessGlobalHint")}</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="block text-sm">
                  <span className="text-surface-muted">{t("admin:benchHarnessPreset")}</span>
                  <select
                    value={globalPreset}
                    onChange={(e) => setGlobalPreset(e.target.value as HarnessPreset)}
                    className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  >
                    <option value="observability">{t("admin:benchHarnessObservability")}</option>
                    <option value="chat_parity">{t("admin:benchHarnessChatParity")}</option>
                  </select>
                </label>
                <label className="block text-sm">
                  <span className="text-surface-muted">{t("admin:benchMaxToolRounds")}</span>
                  <input
                    type="number"
                    min={1}
                    value={globalMaxRounds}
                    onChange={(e) => setGlobalMaxRounds(e.target.value)}
                    placeholder={t("admin:harnessInheritPlaceholder")}
                    className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  />
                </label>
                <label className="block text-sm md:col-span-2">
                  <span className="text-surface-muted">{t("admin:benchScenarioTimeout")}</span>
                  <input
                    type="number"
                    min={30}
                    step={30}
                    value={globalTimeout}
                    onChange={(e) => setGlobalTimeout(e.target.value)}
                    placeholder={t("admin:harnessInheritPlaceholder")}
                    className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  />
                </label>
                <label className="block text-sm md:col-span-2">
                  <span className="text-surface-muted">{t("admin:harnessNotes")}</span>
                  <textarea
                    value={globalNotes}
                    onChange={(e) => setGlobalNotes(e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onSaveGlobal()}
                className="mt-4 rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {t("admin:harnessSaveGlobal")}
              </button>
            </section>

            <section className="rounded-lg border border-white/10 bg-black/20 p-4">
              <h2 className="text-sm font-medium text-white">{t("admin:harnessOverridesTitle")}</h2>
              <p className="mt-1 text-xs text-surface-muted">{t("admin:harnessOverridesHint")}</p>

              {overrides.length ? (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-surface-muted">
                      <tr>
                        <th className="pb-2 pr-3">{t("admin:harnessColProvider")}</th>
                        <th className="pb-2 pr-3">{t("admin:harnessColModel")}</th>
                        <th className="pb-2 pr-3">{t("admin:benchHarnessPreset")}</th>
                        <th className="pb-2 pr-3">{t("admin:benchMaxToolRounds")}</th>
                        <th className="pb-2 pr-3">{t("admin:benchScenarioTimeout")}</th>
                        <th className="pb-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {overrides.map((row) => (
                        <tr key={row.id} className="border-t border-white/5">
                          <td className="py-2 pr-3 font-mono text-xs">{row.catalog_owned_by}</td>
                          <td className="py-2 pr-3 font-mono text-xs">
                            {row.model || <span className="text-surface-muted">*</span>}
                          </td>
                          <td className="py-2 pr-3">{row.harness_preset}</td>
                          <td className="py-2 pr-3">{row.max_tool_rounds_override ?? "—"}</td>
                          <td className="py-2 pr-3">{row.scenario_timeout_sec ?? "—"}</td>
                          <td className="py-2 text-right">
                            <button
                              type="button"
                              className="text-sky-400 hover:underline"
                              onClick={() => startEdit(row)}
                            >
                              {t("admin:harnessEdit")}
                            </button>
                            <button
                              type="button"
                              className="ml-3 text-red-400 hover:underline"
                              onClick={() => void onDeleteOverride(row.id)}
                            >
                              {t("admin:harnessDelete")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-4 text-sm text-surface-muted">{t("admin:harnessNoOverrides")}</p>
              )}

              <div className="mt-6 border-t border-white/10 pt-4">
                <h3 className="text-sm text-white">
                  {editingId ? t("admin:harnessEditOverride") : t("admin:harnessAddOverride")}
                </h3>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:harnessColProvider")}</span>
                    <select
                      value={overrideForm.catalog_owned_by}
                      onChange={(e) =>
                        setOverrideForm((f) => ({ ...f, catalog_owned_by: e.target.value }))
                      }
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    >
                      <option value="">{t("admin:harnessSelectProvider")}</option>
                      {benchProviders.map((p) => (
                        <option key={p.catalog_owned_by} value={p.catalog_owned_by}>
                          {p.label || p.catalog_owned_by}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:harnessColModel")}</span>
                    <input
                      value={overrideForm.model}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, model: e.target.value }))}
                      placeholder={t("admin:harnessModelWildcardHint")}
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:harnessLabel")}</span>
                    <input
                      value={overrideForm.label}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, label: e.target.value }))}
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:benchHarnessPreset")}</span>
                    <select
                      value={overrideForm.harness_preset}
                      onChange={(e) =>
                        setOverrideForm((f) => ({
                          ...f,
                          harness_preset: e.target.value as HarnessPreset,
                        }))
                      }
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    >
                      <option value="observability">{t("admin:benchHarnessObservability")}</option>
                      <option value="chat_parity">{t("admin:benchHarnessChatParity")}</option>
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:benchMaxToolRounds")}</span>
                    <input
                      type="number"
                      min={1}
                      value={
                        overrideForm.max_tool_rounds_override != null
                          ? String(overrideForm.max_tool_rounds_override)
                          : ""
                      }
                      onChange={(e) =>
                        setOverrideForm((f) => ({
                          ...f,
                          max_tool_rounds_override: parseOptionalInt(e.target.value),
                        }))
                      }
                      placeholder={t("admin:harnessInheritPlaceholder")}
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-surface-muted">{t("admin:benchScenarioTimeout")}</span>
                    <input
                      type="number"
                      min={30}
                      step={30}
                      value={
                        overrideForm.scenario_timeout_sec != null
                          ? String(overrideForm.scenario_timeout_sec)
                          : ""
                      }
                      onChange={(e) =>
                        setOverrideForm((f) => ({
                          ...f,
                          scenario_timeout_sec: parseOptionalFloat(e.target.value),
                        }))
                      }
                      placeholder={t("admin:harnessInheritPlaceholder")}
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                  <label className="block text-sm md:col-span-2">
                    <span className="text-surface-muted">{t("admin:harnessNotes")}</span>
                    <textarea
                      value={overrideForm.notes || ""}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, notes: e.target.value }))}
                      rows={2}
                      className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                    />
                  </label>
                </div>
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onSaveOverride()}
                    className="rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500 disabled:opacity-50"
                  >
                    {editingId ? t("admin:harnessUpdateOverride") : t("admin:harnessAddOverrideBtn")}
                  </button>
                  {editingId ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={resetOverrideForm}
                      className="rounded border border-white/10 px-3 py-1.5 text-sm text-surface-muted hover:text-white"
                    >
                      {t("admin:cancel")}
                    </button>
                  ) : null}
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
