import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../../auth/AuthContext";
import { formatBenchmarkProviderModel } from "./benchDisplayUtils";
import {
  fetchBenchmarkStats,
  type BenchmarkStatsModelRow,
  type BenchmarkStatsPayload,
  type BenchmarkStatsScenarioGroup,
} from "./benchmarksApi";

const SINCE_DAY_OPTIONS = [
  { value: "", labelKey: "admin:benchStatsSinceAll" },
  { value: "7", labelKey: "admin:benchStatsSince7d" },
  { value: "30", labelKey: "admin:benchStatsSince30d" },
  { value: "90", labelKey: "admin:benchStatsSince90d" },
  { value: "365", labelKey: "admin:benchStatsSince365d" },
] as const;

const BADGE_MIN_SAMPLE_OPTIONS = [
  { value: "1", labelKey: "admin:benchStatsMinSamples1" },
  { value: "2", labelKey: "admin:benchStatsMinSamples2" },
  { value: "3", labelKey: "admin:benchStatsMinSamples3" },
  { value: "5", labelKey: "admin:benchStatsMinSamples5" },
] as const;

const FASTEST_PASS_OPTIONS = [
  { value: "0", labelKey: "admin:benchStatsFastestAnyPass" },
  { value: "0.5", labelKey: "admin:benchStatsFastestHalfPass" },
  { value: "1", labelKey: "admin:benchStatsFastestFullPass" },
] as const;

const MIN_SAMPLE_OPTIONS = BADGE_MIN_SAMPLE_OPTIONS;

function formatPassRate(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

function formatMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}`;
}

function filterStatsPayload(
  stats: BenchmarkStatsPayload | null,
  minSamples: number
): { models: BenchmarkStatsModelRow[]; by_scenario: BenchmarkStatsScenarioGroup[] } {
  if (!stats) return { models: [], by_scenario: [] };
  const models =
    minSamples <= 1 ? stats.models : stats.models.filter((m) => m.samples >= minSamples);
  const by_scenario = stats.by_scenario
    .map((group) => ({
      ...group,
      models:
        minSamples <= 1
          ? group.models
          : group.models.filter((m) => m.samples >= minSamples),
    }))
    .filter((group) => group.models.length > 0);
  return { models, by_scenario };
}

function PassRateBadge({ rate }: { rate: number | null | undefined }) {
  if (rate == null) return <span className="text-surface-muted">—</span>;
  const pct = Math.round(rate * 100);
  const tone =
    pct >= 90 ? "text-emerald-300" : pct >= 60 ? "text-amber-200" : "text-rose-300";
  return <span className={tone}>{pct}%</span>;
}

function ModelLeaderboardTable({
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
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead>
          <tr className="text-surface-muted">
            <th className="py-1 pr-3">#</th>
            <th className="py-1 pr-3">{t("admin:benchColProviderModel")}</th>
            <th className="py-1 pr-3">{t("admin:benchStatsRuns")}</th>
            <th className="py-1 pr-3">{t("admin:benchStatsSamples")}</th>
            <th className="py-1 pr-3">{t("admin:benchStatsPassRate")}</th>
            <th className="py-1 pr-3">{t("admin:benchColMs")} Ø</th>
            <th className="py-1 pr-3">{t("admin:benchStatsMedianMs")}</th>
            <th className="py-1 pr-3">{t("admin:benchStatsBestMs")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${row.catalog_owned_by}:${row.model}`} className="border-t border-white/5">
              <td className="py-1.5 pr-3 text-surface-muted">{idx + 1}</td>
              <td className="py-1.5 pr-3 font-mono text-[11px]">{formatBenchmarkProviderModel(row)}</td>
              <td className="py-1.5 pr-3">{row.runs}</td>
              <td className="py-1.5 pr-3">
                {row.samples}
                {row.skipped > 0 ? (
                  <span className="ml-1 text-surface-muted">
                    (+{row.skipped} {t("admin:benchStatsSkipped")})
                  </span>
                ) : null}
              </td>
              <td className="py-1.5 pr-3">
                <PassRateBadge rate={row.pass_rate} />
                <span className="ml-1 text-surface-muted">
                  {row.passed}/{row.samples}
                </span>
              </td>
              <td className="py-1.5 pr-3">{formatMs(row.avg_latency_ms)}</td>
              <td className="py-1.5 pr-3">{formatMs(row.median_latency_ms)}</td>
              <td className="py-1.5 pr-3 text-emerald-300/90">{formatMs(row.min_latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScenarioGroupCard({
  group,
  showSuite,
  t,
}: {
  group: BenchmarkStatsScenarioGroup;
  showSuite: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const title = showSuite ? `${group.suite} · ${group.scenario_id}` : group.scenario_id;
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm text-white">{title}</h3>
        <div className="flex flex-wrap gap-3 text-[11px] text-surface-muted">
          {group.fastest ? (
            <span>
              {t("admin:benchStatsFastestPassing")}:{" "}
              <span className="font-mono text-emerald-300/90">
                {formatBenchmarkProviderModel(group.fastest)} ({formatMs(group.fastest.avg_latency_ms)} ms)
              </span>
            </span>
          ) : null}
          {group.best_pass ? (
            <span>
              {t("admin:benchStatsBestPass")}:{" "}
              <span className="font-mono text-sky-300/90">{formatBenchmarkProviderModel(group.best_pass)}</span>
            </span>
          ) : null}
        </div>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-[11px]">
          <thead>
            <tr className="text-surface-muted">
              <th className="py-1 pr-2">#</th>
              <th className="py-1 pr-2">{t("admin:benchColProviderModel")}</th>
              <th className="py-1 pr-2">{t("admin:benchStatsPassRate")}</th>
              <th className="py-1 pr-2">{t("admin:benchColMs")} Ø</th>
              <th className="py-1 pr-2">{t("admin:benchStatsSamples")}</th>
            </tr>
          </thead>
          <tbody>
            {group.models.map((row, idx) => (
              <tr key={`${row.catalog_owned_by}:${row.model}`} className="border-t border-white/5">
                <td className="py-1 pr-2 text-surface-muted">{idx + 1}</td>
                <td className="py-1 pr-2 font-mono">{formatBenchmarkProviderModel(row)}</td>
                <td className="py-1 pr-2">
                  <PassRateBadge rate={row.pass_rate} />
                </td>
                <td className="py-1 pr-2">{formatMs(row.avg_latency_ms)}</td>
                <td className="py-1 pr-2">{row.samples}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function BenchmarkStatsPanel({
  auth,
  onClearHistory,
  clearHistoryDisabled = false,
  refreshToken = 0,
}: {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  onClearHistory?: (prefill?: { suite?: string }) => void;
  clearHistoryDisabled?: boolean;
  refreshToken?: number;
}) {
  const { t } = useTranslation();
  const [stats, setStats] = useState<BenchmarkStatsPayload | null>(null);
  const [suiteFilter, setSuiteFilter] = useState("");
  const [sinceDays, setSinceDays] = useState("");
  const [minSamples, setMinSamples] = useState("1");
  const [badgeMinSamples, setBadgeMinSamples] = useState("2");
  const [fastestMinPassRate, setFastestMinPassRate] = useState("0");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sinceParsed = sinceDays ? Number(sinceDays) : undefined;
      const badgeParsed = Math.max(1, Number(badgeMinSamples) || 2);
      const fastestParsed = Number(fastestMinPassRate);
      const data = await fetchBenchmarkStats(auth, {
        limit: 200,
        suite: suiteFilter || undefined,
        sinceDays: sinceParsed && sinceParsed >= 1 ? sinceParsed : undefined,
        badgeMinSamples: badgeParsed,
        fastestMinPassRate: Number.isFinite(fastestParsed) ? fastestParsed : 0,
      });
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchLoadFailed"));
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [auth, suiteFilter, sinceDays, badgeMinSamples, fastestMinPassRate, t]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (refreshToken > 0) void loadStats();
  }, [refreshToken, loadStats]);

  const suiteOptions = useMemo(() => {
    const fromMeta = stats?.meta.suites ?? [];
    return ["", ...fromMeta];
  }, [stats?.meta.suites]);

  const minSamplesNum = Math.max(1, Number(minSamples) || 1);
  const filtered = useMemo(
    () => filterStatsPayload(stats, minSamplesNum),
    [stats, minSamplesNum]
  );

  const showSuiteInScenario = (stats?.meta.suite_filter ?? "") === "";

  const fastestQualifyLabel = useMemo(() => {
    const opt = FASTEST_PASS_OPTIONS.find((o) => o.value === fastestMinPassRate);
    return opt ? t(opt.labelKey) : t("admin:benchStatsFastestAnyPass");
  }, [fastestMinPassRate, t]);

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
      <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-white">{t("admin:benchStatsTitle")}</h2>
            <p className="mt-1 text-xs text-surface-muted">{t("admin:benchStatsHint")}</p>
            <p className="mt-1 text-[11px] text-surface-muted">{t("admin:benchStatsClearHint")}</p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            {onClearHistory ? (
              <button
                type="button"
                onClick={() => onClearHistory({ suite: suiteFilter || undefined })}
                disabled={clearHistoryDisabled}
                className="rounded-lg border border-rose-500/30 bg-rose-950/20 px-3 py-1.5 text-xs text-rose-200 hover:bg-rose-950/40 disabled:opacity-40"
              >
                {t("admin:benchBulkDeleteHistory")}
              </button>
            ) : null}
            <label className="text-xs text-surface-muted">
              {t("admin:benchSuite")}
              <select
                value={suiteFilter}
                onChange={(e) => setSuiteFilter(e.target.value)}
                className="mt-1 block rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
              >
                <option value="">{t("admin:benchStatsAllSuites")}</option>
                {suiteOptions
                  .filter(Boolean)
                  .map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
              </select>
            </label>
            <label className="text-xs text-surface-muted">
              {t("admin:benchStatsSince")}
              <select
                value={sinceDays}
                onChange={(e) => setSinceDays(e.target.value)}
                className="mt-1 block rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
              >
                {SINCE_DAY_OPTIONS.map((opt) => (
                  <option key={opt.value || "all"} value={opt.value}>
                    {t(opt.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-surface-muted">
              {t("admin:benchStatsTableMinSamples")}
              <select
                value={minSamples}
                onChange={(e) => setMinSamples(e.target.value)}
                className="mt-1 block rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
              >
                {MIN_SAMPLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {t(opt.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-surface-muted">
              {t("admin:benchStatsBadgeMinSamples")}
              <select
                value={badgeMinSamples}
                onChange={(e) => setBadgeMinSamples(e.target.value)}
                className="mt-1 block rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
              >
                {BADGE_MIN_SAMPLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {t(opt.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-surface-muted">
              {t("admin:benchStatsFastestQualify")}
              <select
                value={fastestMinPassRate}
                onChange={(e) => setFastestMinPassRate(e.target.value)}
                className="mt-1 block max-w-[11rem] rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
              >
                {FASTEST_PASS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {t(opt.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void loadStats()}
              disabled={loading}
              className="rounded-lg border border-white/15 bg-black/30 px-3 py-1.5 text-xs text-white hover:bg-white/10 disabled:opacity-50"
            >
              {loading ? t("admin:loading") : t("admin:agentTracesRefresh")}
            </button>
          </div>
        </div>
        {stats?.meta ? (
          <p className="mt-2 text-[11px] text-surface-muted">
            {t("admin:benchStatsMeta", {
              runs: stats.meta.run_count,
              results: stats.meta.result_count,
            })}
            {stats.meta.since_days
              ? ` · ${t("admin:benchStatsSinceMeta", { days: stats.meta.since_days })}`
              : ""}
            {` · ${t("admin:benchStatsBadgeMeta", {
              minSamples: stats.meta.badge_min_samples ?? 2,
              fastestQualify: fastestQualifyLabel,
            })}`}
          </p>
        ) : null}
        {error ? <p className="mt-2 text-sm text-red-400">{error}</p> : null}
      </section>

      <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
        <h2 className="text-sm font-medium text-white">{t("admin:benchStatsLeaderboard")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("admin:benchStatsLeaderboardHint")}</p>
        <div className="mt-3">
          {loading && !stats ? (
            <p className="text-xs text-surface-muted">{t("admin:loading")}</p>
          ) : (
            <ModelLeaderboardTable rows={filtered.models} t={t} />
          )}
        </div>
      </section>

      <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
        <h2 className="text-sm font-medium text-white">{t("admin:benchStatsByScenario")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("admin:benchStatsByScenarioHint")}</p>
        <div className="mt-3 space-y-3">
          {filtered.by_scenario.length === 0 ? (
            <p className="text-xs text-surface-muted">{t("admin:benchStatsNoData")}</p>
          ) : (
            filtered.by_scenario.map((group) => (
              <ScenarioGroupCard
                key={`${group.suite}:${group.scenario_id}`}
                group={group}
                showSuite={showSuiteInScenario}
                t={t}
              />
            ))
          )}
        </div>
      </section>
    </div>
  );
}
