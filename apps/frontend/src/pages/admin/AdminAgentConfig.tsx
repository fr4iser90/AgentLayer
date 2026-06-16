import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  applyAgentConfigPatches,
  createAgentConfigSession,
  fetchAgentConfigChangelog,
  fetchAgentConfigFingerprint,
  fetchAgentConfigKnobs,
  fetchAgentConfigSessions,
  fetchBenchmarkExperiments,
  type AgentConfigKnob,
  type BenchmarkExperiment,
  isHarnessKnob,
} from "../../features/admin/agentConfig/agentConfigApi";
import { BenchmarkAnalysisPanel } from "../../features/admin/agentConfig/BenchmarkAnalysisPanel";
import { ExperimentDetailPanel } from "../../features/admin/agentConfig/ExperimentDetailPanel";

type Tab = "knobs" | "sessions" | "experiments" | "analysis";

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
  const [sessions, setSessions] = useState<unknown[]>([]);
  const [experiments, setExperiments] = useState<BenchmarkExperiment[]>([]);
  const [sessionLabel, setSessionLabel] = useState("");
  const [sessionCohort, setSessionCohort] = useState("");

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [k, fp, cl, sess, exps] = await Promise.all([
        fetchAgentConfigKnobs(auth),
        fetchAgentConfigFingerprint(auth),
        fetchAgentConfigChangelog(auth),
        fetchAgentConfigSessions(auth),
        fetchBenchmarkExperiments(auth),
      ]);
      setKnobs((k.knobs || []).filter(isHarnessKnob));
      setFingerprint(String(fp.fingerprint || ""));
      setGitSha(String(fp.git_sha || ""));
      setEvents(cl.events || []);
      setSessions(sess.sessions || []);
      setExperiments(exps.experiments || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const selected = knobs.find((k) => k.id === selectedId);

  useEffect(() => {
    if (!selected) {
      setEditValue("");
      return;
    }
    const v = selected.effective ?? selected.default ?? "";
    setEditValue(typeof v === "string" ? v : JSON.stringify(v));
  }, [selected]);

  async function onApply() {
    if (!auth.accessToken || !selectedId || selected?.writable === false) return;
    setApplyBusy(true);
    setError(null);
    try {
      let value: unknown = editValue;
      if (selected?.type === "integer") value = parseInt(editValue, 10);
      else if (selected?.type === "boolean") value = editValue === "true";
      else if (selected?.type === "string_list") value = JSON.parse(editValue || "[]");
      await applyAgentConfigPatches(auth, {
        patches: [{ knob_id: selectedId, value }],
        hypothesis: hypothesis.trim() || undefined,
      });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplyBusy(false);
    }
  }

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
          {(["knobs", "sessions", "experiments", "analysis"] as Tab[]).map((id) => (
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
      ) : tab === "analysis" ? (
        <section className="min-h-0 flex-1 overflow-auto rounded-lg border border-surface-border bg-[#111] p-4">
          <BenchmarkAnalysisPanel auth={auth} />
        </section>
      ) : tab === "sessions" ? (
        <section className="space-y-3 overflow-auto rounded-lg border border-surface-border bg-[#111] p-3">
          <div className="flex flex-wrap gap-2">
            <input
              className="rounded border border-surface-border bg-black/30 p-2 text-sm text-white"
              placeholder={t("admin:agentConfigSessionLabel")}
              value={sessionLabel}
              onChange={(e) => setSessionLabel(e.target.value)}
            />
            <input
              className="rounded border border-surface-border bg-black/30 p-2 text-sm text-white"
              placeholder={t("admin:agentConfigSessionCohort")}
              value={sessionCohort}
              onChange={(e) => setSessionCohort(e.target.value)}
            />
            <button
              type="button"
              className="rounded bg-emerald-700 px-3 py-2 text-sm text-white"
              onClick={() =>
                void (async () => {
                  if (!sessionLabel.trim() || !sessionCohort.trim()) return;
                  await createAgentConfigSession(auth, {
                    label: sessionLabel.trim(),
                    cohort_label: sessionCohort.trim(),
                  });
                  await reload();
                })()
              }
            >
              {t("admin:agentConfigSessionCreate")}
            </button>
          </div>
          <ul className="space-y-2 text-xs">
            {(sessions as { id?: string; label?: string; status?: string }[]).map((s) => (
              <li key={s.id} className="rounded border border-surface-border/60 p-2">
                {s.label} — {s.status}
              </li>
            ))}
          </ul>
        </section>
      ) : tab === "experiments" ? (
        <ExperimentDetailPanel auth={auth} experiments={experiments} onRefresh={() => void reload()} />
      ) : (
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

            <h3 className="mt-4 text-sm font-medium text-white">{t("admin:agentConfigChangelog")}</h3>
            <ul className="space-y-2 text-xs text-surface-muted">
              {(events as { id?: string; at?: string; patches?: unknown[] }[]).slice(0, 10).map((ev) => (
                <li key={ev.id} className="rounded border border-surface-border/60 p-2">
                  <div>{ev.at}</div>
                  <pre className="mt-1 overflow-auto whitespace-pre-wrap">{JSON.stringify(ev.patches, null, 2)}</pre>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
