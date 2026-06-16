import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../../auth/AuthContext";
import { formatBenchmarkProviderModel } from "../benchmarks/benchDisplayUtils";
import type { BenchmarkStatsModelRow } from "../benchmarks/benchmarksApi";
import {
  fetchBenchmarkAnalysis,
  fetchBenchmarkCohortCompare,
  fetchBenchmarkCohorts,
  type BenchmarkAnalysisPayload,
  type BenchmarkCohortRow,
} from "./agentConfigApi";

function formatPassRate(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

function passRateTone(rate: number): string {
  const pct = Math.round(rate * 100);
  if (pct >= 90) return "text-emerald-300";
  if (pct >= 60) return "text-amber-200";
  return "text-rose-300";
}

function PatternBars({
  patterns,
  t,
}: {
  patterns: Record<string, number>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const entries = Object.entries(patterns).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return <p className="text-xs text-surface-muted">{t("admin:agentConfigAnalysisNoPatterns")}</p>;
  }
  const max = Math.max(...entries.map(([, c]) => c), 1);
  return (
    <ul className="space-y-2">
      {entries.map(([pid, count]) => (
        <li key={pid}>
          <div className="mb-0.5 flex justify-between text-xs">
            <span className="font-mono text-white/90">{pid}</span>
            <span className="text-surface-muted">{count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-white/5">
            <div
              className="h-full rounded bg-rose-500/70"
              style={{ width: `${Math.max(8, (count / max) * 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function ModelMiniTable({
  rows,
  t,
}: {
  rows: BenchmarkStatsModelRow[];
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  if (rows.length === 0) {
    return <p className="text-xs text-surface-muted">{t("admin:benchStatsNoData")}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-left text-xs">
        <thead>
          <tr className="text-surface-muted">
            <th className="py-1 pr-3">{t("admin:benchColProviderModel")}</th>
            <th className="py-1 pr-3">{t("admin:benchStatsPassRate")}</th>
            <th className="py-1 pr-3">{t("admin:benchColMs")} Ø</th>
            <th className="py-1 pr-3">{t("admin:benchStatsSamples")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((row) => (
            <tr key={`${row.catalog_owned_by}:${row.model}`} className="border-t border-white/5">
              <td className="py-1.5 pr-3 font-mono text-[11px]">{formatBenchmarkProviderModel(row)}</td>
              <td className={`py-1.5 pr-3 ${passRateTone(row.pass_rate ?? 0)}`}>
                {formatPassRate(row.pass_rate)}
              </td>
              <td className="py-1.5 pr-3">
                {row.avg_latency_ms != null ? Math.round(row.avg_latency_ms) : "—"}
              </td>
              <td className="py-1.5 pr-3">{row.samples}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalysisSummary({
  analysis,
  t,
}: {
  analysis: BenchmarkAnalysisPayload;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const models = analysis.stats?.models ?? [];
  const topModel = models[0];
  const scenarios = analysis.by_scenario ?? [];
  const weak = scenarios.filter((s) => s.pass_rate < 0.6).length;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-lg border border-surface-border bg-black/20 p-3">
        <p className="text-[10px] uppercase text-surface-muted">{t("admin:agentConfigAnalysisRuns")}</p>
        <p className="mt-1 text-xl font-semibold text-white">{analysis.run_count}</p>
      </div>
      <div className="rounded-lg border border-surface-border bg-black/20 p-3">
        <p className="text-[10px] uppercase text-surface-muted">{t("admin:agentConfigAnalysisTopModel")}</p>
        <p className="mt-1 text-sm font-mono text-white truncate">
          {topModel ? formatBenchmarkProviderModel(topModel) : "—"}
        </p>
        {topModel ? (
          <p className={`mt-0.5 text-xs ${passRateTone(topModel.pass_rate ?? 0)}`}>
            {formatPassRate(topModel.pass_rate)}
          </p>
        ) : null}
      </div>
      <div className="rounded-lg border border-surface-border bg-black/20 p-3">
        <p className="text-[10px] uppercase text-surface-muted">{t("admin:agentConfigAnalysisScenarios")}</p>
        <p className="mt-1 text-xl font-semibold text-white">{scenarios.length}</p>
      </div>
      <div className="rounded-lg border border-surface-border bg-black/20 p-3">
        <p className="text-[10px] uppercase text-surface-muted">{t("admin:agentConfigAnalysisWeakScenarios")}</p>
        <p className="mt-1 text-xl font-semibold text-rose-300">{weak}</p>
      </div>
    </div>
  );
}

type Props = {
  auth: AuthContextValue;
  /** When set, analysis is scoped to this experiment (no cohort filter). */
  experimentId?: string;
  /** Pre-loaded analysis (skips initial fetch when provided). */
  initialAnalysis?: BenchmarkAnalysisPayload | null;
  compact?: boolean;
};

export function BenchmarkAnalysisPanel({
  auth,
  experimentId,
  initialAnalysis,
  compact = false,
}: Props) {
  const { t } = useTranslation(["admin"]);
  const [analysis, setAnalysis] = useState<BenchmarkAnalysisPayload | null>(initialAnalysis ?? null);
  const [cohorts, setCohorts] = useState<BenchmarkCohortRow[]>([]);
  const [cohortFilter, setCohortFilter] = useState("");
  const [suiteFilter, setSuiteFilter] = useState("");
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [compareResult, setCompareResult] = useState<{
    a: BenchmarkAnalysisPayload;
    b: BenchmarkAnalysisPayload;
  } | null>(null);
  const [loading, setLoading] = useState(!initialAnalysis);
  const [error, setError] = useState<string | null>(null);

  const loadAnalysis = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBenchmarkAnalysis(auth, {
        cohort: cohortFilter || undefined,
        suite: suiteFilter || undefined,
        experiment_id: experimentId,
      });
      setAnalysis(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, cohortFilter, suiteFilter, experimentId]);

  useEffect(() => {
    if (initialAnalysis) {
      setAnalysis(initialAnalysis);
      return;
    }
    void loadAnalysis();
  }, [initialAnalysis, loadAnalysis]);

  useEffect(() => {
    if (experimentId || !auth.accessToken) return;
    void (async () => {
      try {
        const data = await fetchBenchmarkCohorts(auth);
        setCohorts(data.cohorts ?? []);
      } catch {
        /* optional */
      }
    })();
  }, [auth, experimentId]);

  const suiteOptions = useMemo(() => {
    const suites = analysis?.stats?.meta?.suites ?? [];
    return suites.filter(Boolean);
  }, [analysis]);

  async function onCompare() {
    if (!compareA || !compareB || compareA === compareB) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBenchmarkCohortCompare(auth, compareA, compareB, suiteFilter || undefined);
      setCompareResult({ a: data.a, b: data.b });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const patterns = analysis?.top_patterns ?? {};

  return (
    <div className="flex min-h-0 flex-col gap-4">
      {!experimentId && !compact ? (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-surface-border bg-black/20 p-3">
          <label className="block text-xs">
            <span className="text-surface-muted">{t("admin:agentConfigAnalysisCohortFilter")}</span>
            <select
              value={cohortFilter}
              onChange={(e) => setCohortFilter(e.target.value)}
              className="mt-1 block min-w-[160px] rounded border border-white/10 bg-black/40 px-2 py-1.5 text-sm text-white"
            >
              <option value="">{t("admin:agentConfigAnalysisAllCohorts")}</option>
              {cohorts.map((c) => (
                <option key={c.cohort_label} value={c.cohort_label}>
                  {c.cohort_label} ({c.run_count})
                </option>
              ))}
            </select>
          </label>
          {suiteOptions.length > 0 ? (
            <label className="block text-xs">
              <span className="text-surface-muted">{t("admin:benchSuite")}</span>
              <select
                value={suiteFilter}
                onChange={(e) => setSuiteFilter(e.target.value)}
                className="mt-1 block min-w-[120px] rounded border border-white/10 bg-black/40 px-2 py-1.5 text-sm text-white"
              >
                <option value="">{t("admin:benchStatsAllSuites")}</option>
                {suiteOptions.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            type="button"
            onClick={() => void loadAnalysis()}
            disabled={loading}
            className="rounded bg-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/15 disabled:opacity-50"
          >
            {loading ? t("admin:loading") : t("admin:agentConfigAnalysisRefresh")}
          </button>
        </div>
      ) : null}

      {!experimentId && !compact ? (
        <section className="rounded-lg border border-surface-border bg-black/20 p-3">
          <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
            {t("admin:agentConfigAnalysisCompare")}
          </h3>
          <div className="flex flex-wrap items-end gap-2">
            <select
              value={compareA}
              onChange={(e) => setCompareA(e.target.value)}
              className="rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white"
            >
              <option value="">{t("admin:agentConfigAnalysisCohortA")}</option>
              {cohorts.map((c) => (
                <option key={`a-${c.cohort_label}`} value={c.cohort_label}>
                  {c.cohort_label}
                </option>
              ))}
            </select>
            <span className="text-surface-muted text-xs">vs</span>
            <select
              value={compareB}
              onChange={(e) => setCompareB(e.target.value)}
              className="rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white"
            >
              <option value="">{t("admin:agentConfigAnalysisCohortB")}</option>
              {cohorts.map((c) => (
                <option key={`b-${c.cohort_label}`} value={c.cohort_label}>
                  {c.cohort_label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void onCompare()}
              disabled={!compareA || !compareB || compareA === compareB || loading}
              className="rounded bg-indigo-700/80 px-3 py-1.5 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
            >
              {t("admin:agentConfigAnalysisCompareBtn")}
            </button>
          </div>
          {compareResult ? (
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {(["a", "b"] as const).map((side) => {
                const block = compareResult[side];
                const label = side === "a" ? compareA : compareB;
                return (
                  <div key={side} className="rounded border border-white/10 p-2">
                    <p className="mb-2 text-xs font-medium text-white">{label}</p>
                    <p className="text-xs text-surface-muted">
                      {t("admin:agentConfigAnalysisRuns")}: {block.run_count}
                    </p>
                    <PatternBars patterns={block.top_patterns ?? {}} t={t} />
                  </div>
                );
              })}
            </div>
          ) : null}
        </section>
      ) : null}

      {error ? (
        <p className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      {loading && !analysis ? (
        <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
      ) : analysis ? (
        <>
          <AnalysisSummary analysis={analysis} t={t} />

          <div className="grid min-h-0 gap-4 lg:grid-cols-2">
            <section className="rounded-lg border border-surface-border bg-[#111] p-3">
              <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                {t("admin:agentConfigAnalysisFailurePatterns")}
              </h3>
              <PatternBars patterns={patterns} t={t} />
            </section>

            <section className="rounded-lg border border-surface-border bg-[#111] p-3">
              <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                {t("admin:benchStatsLeaderboard")}
              </h3>
              <ModelMiniTable rows={analysis.stats?.models ?? []} t={t} />
            </section>
          </div>

          {(analysis.by_scenario?.length ?? 0) > 0 ? (
            <section className="rounded-lg border border-surface-border bg-[#111] p-3">
              <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                {t("admin:agentConfigAnalysisByScenario")}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-xs">
                  <thead>
                    <tr className="text-surface-muted">
                      <th className="py-1 pr-3">{t("admin:benchColScenario")}</th>
                      <th className="py-1 pr-3">{t("admin:benchStatsPassRate")}</th>
                      <th className="py-1 pr-3">{t("admin:agentConfigAnalysisPatterns")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(analysis.by_scenario ?? []).map((row) => (
                      <tr key={row.scenario_id} className="border-t border-white/5">
                        <td className="py-1.5 pr-3 font-mono">{row.scenario_id}</td>
                        <td className={`py-1.5 pr-3 ${passRateTone(row.pass_rate)}`}>
                          {formatPassRate(row.pass_rate)}
                        </td>
                        <td className="py-1.5 pr-3 font-mono text-[10px] text-surface-muted">
                          {row.patterns.length ? row.patterns.join(", ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {analysis.run_count === 0 ? (
            <p className="text-sm text-surface-muted">{t("admin:agentConfigAnalysisNoRuns")}</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
