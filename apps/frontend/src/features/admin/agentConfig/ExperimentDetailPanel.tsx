import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { AuthContextValue } from "../../../auth/AuthContext";
import {
  fetchBenchmarkExperimentReport,
  submitBenchmarkReview,
  type BenchmarkExperiment,
  type BenchmarkExperimentReport,
  type BenchmarkReview,
} from "../benchmarks/benchmarksApi";

function verdictTone(verdict: string | undefined): string {
  const v = (verdict || "").toLowerCase();
  if (v === "accept") return "text-emerald-300 bg-emerald-950/40 border-emerald-500/30";
  if (v === "reject" || v === "regression_tool_calling") return "text-rose-300 bg-rose-950/40 border-rose-500/30";
  if (v === "mixed") return "text-amber-200 bg-amber-950/30 border-amber-500/30";
  return "text-surface-muted bg-white/5 border-white/10";
}

function ReviewCard({ review }: { review: BenchmarkReview }) {
  return (
    <li className={`rounded border p-3 ${verdictTone(review.verdict)}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium uppercase">{review.verdict ?? "—"}</span>
        {review.mode ? <span className="opacity-70">· {review.mode}</span> : null}
        {review.created_at ? (
          <span className="opacity-60">{new Date(review.created_at).toLocaleString()}</span>
        ) : null}
      </div>
      {review.summary ? <p className="mt-2 text-sm whitespace-pre-wrap">{review.summary}</p> : null}
      {review.patterns_json && Object.keys(review.patterns_json).length > 0 ? (
        <p className="mt-2 font-mono text-[10px] opacity-80">
          {Object.entries(review.patterns_json)
            .map(([k, v]) => `${k}:${v}`)
            .join(" · ")}
        </p>
      ) : null}
    </li>
  );
}

type Props = {
  auth: AuthContextValue;
  experiments: BenchmarkExperiment[];
  onRefresh?: () => void;
};

export function ExperimentDetailPanel({ auth, experiments }: Props) {
  const { t } = useTranslation(["admin"]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [report, setReport] = useState<BenchmarkExperimentReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewSummary, setReviewSummary] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const selected = experiments.find((e) => e.id === selectedId);

  const loadReport = useCallback(
    async (id: string) => {
      if (!auth.accessToken || !id) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchBenchmarkExperimentReport(auth, id);
        setReport({
          experiment: data.experiment,
          analysis: data.analysis,
          reviews: data.reviews ?? [],
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setReport(null);
      } finally {
        setLoading(false);
      }
    },
    [auth],
  );

  useEffect(() => {
    if (!selectedId && experiments[0]?.id) {
      setSelectedId(experiments[0].id);
    }
  }, [experiments, selectedId]);

  useEffect(() => {
    if (selectedId) void loadReport(selectedId);
  }, [selectedId, loadReport]);

  const runIds = report?.experiment?.run_ids_json ?? selected?.run_ids_json ?? [];

  async function onSubmitReview() {
    if (!selectedId || !auth.accessToken) return;
    setReviewBusy(true);
    setReviewError(null);
    try {
      await submitBenchmarkReview(auth, {
        experiment_id: selectedId,
        run_ids: runIds.length ? runIds : undefined,
        mode: "deterministic",
        summary_hint: reviewSummary.trim() || undefined,
      });
      setReviewSummary("");
      await loadReport(selectedId);
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewBusy(false);
    }
  }

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(200px,280px)_1fr]">
      <section className="min-h-0 overflow-auto rounded-lg border border-surface-border bg-[#111] p-2">
        <h2 className="mb-2 px-1 text-xs font-medium uppercase text-surface-muted">
          {t("admin:agentConfigExperimentsList")}
        </h2>
        {experiments.length === 0 ? (
          <p className="px-1 text-xs text-surface-muted">{t("admin:agentConfigExperimentsEmpty")}</p>
        ) : (
          <ul className="space-y-1">
            {experiments.map((exp) => (
              <li key={exp.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(exp.id)}
                  className={`w-full rounded px-2 py-2 text-left text-xs ${
                    selectedId === exp.id ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5"
                  }`}
                >
                  <div className="font-medium">{exp.label}</div>
                  <div className="mt-0.5 opacity-70">
                    {exp.status ?? "open"}
                    {(exp.run_ids_json?.length ?? 0) > 0
                      ? ` · ${exp.run_ids_json!.length} ${t("admin:agentConfigExperimentRuns")}`
                      : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="min-h-0 overflow-auto rounded-lg border border-surface-border bg-[#111] p-4">
        {!selected ? (
          <p className="text-sm text-surface-muted">{t("admin:agentConfigExperimentSelect")}</p>
        ) : (
          <>
            <header className="mb-4 border-b border-white/10 pb-3">
              <h2 className="text-base font-medium text-white">{selected.label}</h2>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-surface-muted">
                <span className="rounded bg-white/5 px-2 py-0.5">{selected.status ?? "open"}</span>
                {selected.suite_preset ? (
                  <span className="rounded bg-white/5 px-2 py-0.5">suite: {selected.suite_preset}</span>
                ) : null}
                {selected.harness_preset ? (
                  <span className="rounded bg-white/5 px-2 py-0.5">harness: {selected.harness_preset}</span>
                ) : null}
              </div>
              {selected.hypothesis ? (
                <p className="mt-2 text-sm text-surface-muted">{selected.hypothesis}</p>
              ) : null}
              {selected.fingerprint_at_start ? (
                <p className="mt-2 font-mono text-[10px] text-surface-muted break-all">
                  {t("admin:agentConfigExperimentFingerprint")}: {selected.fingerprint_at_start}
                </p>
              ) : null}
            </header>

            {error ? (
              <p className="mb-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                {error}
              </p>
            ) : null}

            {loading ? (
              <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
            ) : report ? (
              <div className="space-y-6">
                {(report.experiment.pending_patches_json?.length ?? 0) > 0 ? (
                  <section>
                    <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                      {t("admin:agentConfigExperimentPendingPatches")}
                    </h3>
                    <pre className="max-h-40 overflow-auto rounded border border-white/10 bg-black/30 p-2 text-[10px] text-surface-muted">
                      {JSON.stringify(report.experiment.pending_patches_json, null, 2)}
                    </pre>
                  </section>
                ) : null}

                {runIds.length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                      {t("admin:agentConfigExperimentRuns")}
                    </h3>
                    <ul className="flex flex-wrap gap-2">
                      {runIds.map((rid) => (
                        <li key={rid}>
                          <Link
                            to={`/admin/benchmarks?run=${encodeURIComponent(rid)}`}
                            className="rounded border border-white/10 bg-black/30 px-2 py-1 font-mono text-[10px] text-indigo-300 hover:bg-white/5"
                            title={rid}
                          >
                            {rid.slice(0, 8)}…
                          </Link>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-1 text-[10px] text-surface-muted">
                      {t("admin:agentConfigExperimentRunsHint")}
                    </p>
                  </section>
                ) : null}

                <section>
                  <h3 className="mb-3 text-xs font-medium uppercase text-surface-muted">
                    {t("admin:agentConfigTab_analysis")}
                  </h3>
                  <p className="text-xs text-surface-muted">
                    {t("admin:agentConfigAnalysisRuns")}: {report.analysis.run_count}
                  </p>
                </section>

                <section>
                  <h3 className="mb-2 text-xs font-medium uppercase text-surface-muted">
                    {t("admin:agentConfigExperimentReviews")}
                  </h3>
                  <div className="mb-4 rounded-lg border border-surface-border bg-black/20 p-3">
                    <p className="mb-2 text-xs text-surface-muted">{t("admin:agentConfigReviewSubmitHint")}</p>
                    <textarea
                      className="mb-2 min-h-[72px] w-full rounded border border-white/10 bg-black/30 p-2 text-sm text-white"
                      placeholder={t("admin:agentConfigReviewSummaryPlaceholder")}
                      value={reviewSummary}
                      onChange={(e) => setReviewSummary(e.target.value)}
                    />
                    {reviewError ? (
                      <p className="mb-2 text-xs text-red-300">{reviewError}</p>
                    ) : null}
                    <button
                      type="button"
                      disabled={reviewBusy || runIds.length === 0}
                      onClick={() => void onSubmitReview()}
                      className="rounded bg-indigo-700 px-3 py-1.5 text-xs text-white hover:bg-indigo-600 disabled:opacity-50"
                    >
                      {reviewBusy ? t("admin:agentConfigReviewSubmitting") : t("admin:agentConfigReviewSubmit")}
                    </button>
                    {runIds.length === 0 ? (
                      <p className="mt-2 text-[10px] text-surface-muted">{t("admin:agentConfigReviewNeedsRuns")}</p>
                    ) : null}
                  </div>
                  {report.reviews.length === 0 ? (
                    <p className="text-xs text-surface-muted">{t("admin:agentConfigExperimentNoReviews")}</p>
                  ) : (
                    <ul className="space-y-2">
                      {report.reviews.map((rev) => (
                        <ReviewCard key={rev.id} review={rev} />
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
