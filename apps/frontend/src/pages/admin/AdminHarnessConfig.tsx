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
import { Button } from "../../ui/Button";

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
      <header className="shrink-0 border-b border-line px-wide py-soft">
        <h1 className="text-lg font-semibold text-ink-primary">{t("admin:harnessTitle")}</h1>
        <p className="mt-tight text-sm text-ink-muted">{t("admin:harnessSubtitle")}</p>
        <p className="mt-base text-xs text-ink-muted">
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

      <div className="min-h-0 flex-1 overflow-y-auto p-wide">
        {error ? (
          <p className="mb-wide rounded-tile border border-red-500/40 bg-red-950/30 px-soft py-base text-sm text-red-200">
            {error}
          </p>
        ) : null}
        {loading ? (
          <p className="text-sm text-ink-muted">{t("admin:loading")}</p>
        ) : (
          <div className="mx-auto max-w-page space-y-deep">
            <section className="rounded-card border border-line bg-black/20 p-wide">
              <h2 className="text-sm font-medium text-ink-primary">{t("admin:harnessGlobalTitle")}</h2>
              <p className="mt-tight text-xs text-ink-muted">{t("admin:harnessGlobalHint")}</p>
              <div className="mt-wide grid gap-wide md:grid-cols-2">
                <label className="block text-sm">
                  <span className="text-ink-muted">{t("admin:benchHarnessPreset")}</span>
                  <select
                    value={globalPreset}
                    onChange={(e) => setGlobalPreset(e.target.value as HarnessPreset)}
                    className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  >
                    <option value="observability">{t("admin:benchHarnessObservability")}</option>
                    <option value="chat_parity">{t("admin:benchHarnessChatParity")}</option>
                  </select>
                </label>
                <label className="block text-sm">
                  <span className="text-ink-muted">{t("admin:benchMaxToolRounds")}</span>
                  <input
                    type="number"
                    min={1}
                    value={globalMaxRounds}
                    onChange={(e) => setGlobalMaxRounds(e.target.value)}
                    placeholder={t("admin:harnessInheritPlaceholder")}
                    className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  />
                </label>
                <label className="block text-sm md:col-span-2">
                  <span className="text-ink-muted">{t("admin:benchScenarioTimeout")}</span>
                  <input
                    type="number"
                    min={30}
                    step={30}
                    value={globalTimeout}
                    onChange={(e) => setGlobalTimeout(e.target.value)}
                    placeholder={t("admin:harnessInheritPlaceholder")}
                    className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  />
                </label>
                <label className="block text-sm md:col-span-2">
                  <span className="text-ink-muted">{t("admin:harnessNotes")}</span>
                  <textarea
                    value={globalNotes}
                    onChange={(e) => setGlobalNotes(e.target.value)}
                    rows={2}
                    className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onSaveGlobal()}
                className="mt-wide rounded-tile bg-sky-600 px-soft py-snug text-sm text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
              >
                {t("admin:harnessSaveGlobal")}
              </button>
            </section>

            <section className="rounded-card border border-line bg-black/20 p-wide">
              <h2 className="text-sm font-medium text-ink-primary">{t("admin:harnessOverridesTitle")}</h2>
              <p className="mt-tight text-xs text-ink-muted">{t("admin:harnessOverridesHint")}</p>

              {overrides.length ? (
                <div className="mt-wide overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-ink-muted">
                      <tr>
                        <th className="pb-base pr-soft">{t("admin:harnessColProvider")}</th>
                        <th className="pb-base pr-soft">{t("admin:harnessColModel")}</th>
                        <th className="pb-base pr-soft">{t("admin:benchHarnessPreset")}</th>
                        <th className="pb-base pr-soft">{t("admin:benchMaxToolRounds")}</th>
                        <th className="pb-base pr-soft">{t("admin:benchScenarioTimeout")}</th>
                        <th className="pb-base" />
                      </tr>
                    </thead>
                    <tbody>
                      {overrides.map((row) => (
                        <tr key={row.id} className="border-t border-line-subtle">
                          <td className="py-base pr-soft font-mono text-xs">{row.catalog_owned_by}</td>
                          <td className="py-base pr-soft font-mono text-xs">
                            {row.model || <span className="text-ink-muted">*</span>}
                          </td>
                          <td className="py-base pr-soft">{row.harness_preset}</td>
                          <td className="py-base pr-soft">{row.max_tool_rounds_override ?? "—"}</td>
                          <td className="py-base pr-soft">{row.scenario_timeout_sec ?? "—"}</td>
                          <td className="py-base text-right">
                            <button
                              type="button"
                              className="text-sky-400 hover:underline"
                              onClick={() => startEdit(row)}
                            >
                              {t("admin:harnessEdit")}
                            </button>
                            <Button
                              type="button"
                              variant="danger"
                              size="sm"
                              className="ml-soft"
                              onClick={() => void onDeleteOverride(row.id)}
                            >
                              {t("admin:harnessDelete")}
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-wide text-sm text-ink-muted">{t("admin:harnessNoOverrides")}</p>
              )}

              <div className="mt-broad border-t border-line pt-wide">
                <h3 className="text-sm text-ink-primary">
                  {editingId ? t("admin:harnessEditOverride") : t("admin:harnessAddOverride")}
                </h3>
                <div className="mt-soft grid gap-soft md:grid-cols-2">
                  <label className="block text-sm">
                    <span className="text-ink-muted">{t("admin:harnessColProvider")}</span>
                    <select
                      value={overrideForm.catalog_owned_by}
                      onChange={(e) =>
                        setOverrideForm((f) => ({ ...f, catalog_owned_by: e.target.value }))
                      }
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
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
                    <span className="text-ink-muted">{t("admin:harnessColModel")}</span>
                    <input
                      value={overrideForm.model}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, model: e.target.value }))}
                      placeholder={t("admin:harnessModelWildcardHint")}
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-ink-muted">{t("admin:harnessLabel")}</span>
                    <input
                      value={overrideForm.label}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, label: e.target.value }))}
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-ink-muted">{t("admin:benchHarnessPreset")}</span>
                    <select
                      value={overrideForm.harness_preset}
                      onChange={(e) =>
                        setOverrideForm((f) => ({
                          ...f,
                          harness_preset: e.target.value as HarnessPreset,
                        }))
                      }
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    >
                      <option value="observability">{t("admin:benchHarnessObservability")}</option>
                      <option value="chat_parity">{t("admin:benchHarnessChatParity")}</option>
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="text-ink-muted">{t("admin:benchMaxToolRounds")}</span>
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
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-ink-muted">{t("admin:benchScenarioTimeout")}</span>
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
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    />
                  </label>
                  <label className="block text-sm md:col-span-2">
                    <span className="text-ink-muted">{t("admin:harnessNotes")}</span>
                    <textarea
                      value={overrideForm.notes || ""}
                      onChange={(e) => setOverrideForm((f) => ({ ...f, notes: e.target.value }))}
                      rows={2}
                      className="mt-tight w-full rounded-tile border border-line bg-field px-base py-snug text-sm text-ink-primary"
                    />
                  </label>
                </div>
                <div className="mt-wide flex gap-base">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onSaveOverride()}
                    className="rounded-tile bg-sky-600 px-soft py-snug text-sm text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
                  >
                    {editingId ? t("admin:harnessUpdateOverride") : t("admin:harnessAddOverrideBtn")}
                  </button>
                  {editingId ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="md"
                      disabled={busy}
                      onClick={resetOverrideForm}
                    >
                      {t("admin:cancel")}
                    </Button>
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
