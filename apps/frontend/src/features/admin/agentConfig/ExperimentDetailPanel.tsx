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
  return "text-ink-muted bg-white/5 border-line";
}

function ReviewCard({ review }: { review: BenchmarkReview }) {
  return (
    <li className={`rounded-tile border p-soft ${verdictTone(review.verdict)}`}>
      <div className="flex flex-wrap items-center gap-base text-xs">
        <span className="font-medium uppercase">{review.verdict ?? "—"}</span>
        {review.mode ? <span className="opacity-70">· {review.mode}</span> : null}
        {review.created_at ? (
          <span className="opacity-60">{new Date(review.created_at).toLocaleString()}</span>
        ) : null}
      </div>
      {review.summary ? <p className="mt-base text-sm whitespace-pre-wrap">{review.summary}</p> : null}
      {review.patterns_json && Object.keys(review.patterns_json).length > 0 ? (
        <p className="mt-base font-mono text-meta opacity-80">
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
    <div className="grid min-h-0 flex-1 gap-wide lg:grid-cols-[minmax(200px,280px)_1fr]">
      <section className="min-h-0 overflow-auto rounded-card border border-line bg-[#111] p-base">
        <h2 className="mb-base px-tight text-xs font-medium uppercase text-ink-muted">
          {t("admin:agentConfigExperimentsList")}
        </h2>
        {experiments.length === 0 ? (
          <p className="px-tight text-xs text-ink-muted">{t("admin:agentConfigExperimentsEmpty")}</p>
        ) : (
          <ul className="space-y-tight">
            {experiments.map((exp) => (
              <li key={exp.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(exp.id)}
                  className={`w-full rounded-tile px-base py-base text-left text-xs ${
                    selectedId === exp.id ? "bg-white/10 text-ink-primary" : "text-ink-muted hover:bg-white/5"
                  }`}
                >
                  <div className="font-medium">{exp.label}</div>
                  <div className="mt-hair opacity-70">
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

      <section className="min-h-0 overflow-auto rounded-card border border-line bg-[#111] p-wide">
        {!selected ? (
          <p className="text-sm text-ink-muted">{t("admin:agentConfigExperimentSelect")}</p>
        ) : (
          <>
            <header className="mb-wide border-b border-line pb-soft">
              <h2 className="text-base font-medium text-ink-primary">{selected.label}</h2>
              <div className="mt-base flex flex-wrap gap-base text-xs text-ink-muted">
                <span className="rounded-tile bg-white/5 px-base py-hair">{selected.status ?? "open"}</span>
                {selected.suite_preset ? (
                  <span className="rounded-tile bg-white/5 px-base py-hair">suite: {selected.suite_preset}</span>
                ) : null}
                {selected.harness_preset ? (
                  <span className="rounded-tile bg-white/5 px-base py-hair">harness: {selected.harness_preset}</span>
                ) : null}
              </div>
              {selected.hypothesis ? (
                <p className="mt-base text-sm text-ink-muted">{selected.hypothesis}</p>
              ) : null}
              {selected.fingerprint_at_start ? (
                <p className="mt-base font-mono text-meta text-ink-muted break-all">
                  {t("admin:agentConfigExperimentFingerprint")}: {selected.fingerprint_at_start}
                </p>
              ) : null}
            </header>

            {error ? (
              <p className="mb-soft rounded-tile border border-red-500/40 bg-red-500/10 px-soft py-base text-sm text-red-200">
                {error}
              </p>
            ) : null}

            {loading ? (
              <p className="text-sm text-ink-muted">{t("admin:loading")}</p>
            ) : report ? (
              <div className="space-y-broad">
                {(report.experiment.pending_patches_json?.length ?? 0) > 0 ? (
                  <section>
                    <h3 className="mb-base text-xs font-medium uppercase text-ink-muted">
                      {t("admin:agentConfigExperimentPendingPatches")}
                    </h3>
                    <pre className="max-h-40 overflow-auto rounded-tile border border-line bg-black/30 p-base text-meta text-ink-muted">
                      {JSON.stringify(report.experiment.pending_patches_json, null, 2)}
                    </pre>
                  </section>
                ) : null}

                {runIds.length > 0 ? (
                  <section>
                    <h3 className="mb-base text-xs font-medium uppercase text-ink-muted">
                      {t("admin:agentConfigExperimentRuns")}
                    </h3>
                    <ul className="flex flex-wrap gap-base">
                      {runIds.map((rid) => (
                        <li key={rid}>
                          <Link
                            to={`/admin/benchmarks?run=${encodeURIComponent(rid)}`}
                            className="rounded-tile border border-line bg-black/30 px-base py-tight font-mono text-meta text-indigo-300 hover:bg-white/5"
                            title={rid}
                          >
                            {rid.slice(0, 8)}…
                          </Link>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-tight text-meta text-ink-muted">
                      {t("admin:agentConfigExperimentRunsHint")}
                    </p>
                  </section>
                ) : null}

                <section>
                  <h3 className="mb-soft text-xs font-medium uppercase text-ink-muted">
                    {t("admin:agentConfigTab_analysis")}
                  </h3>
                  <p className="text-xs text-ink-muted">
                    {t("admin:agentConfigAnalysisRuns")}: {report.analysis.run_count}
                  </p>
                </section>

                <section>
                  <h3 className="mb-base text-xs font-medium uppercase text-ink-muted">
                    {t("admin:agentConfigExperimentReviews")}
                  </h3>
                  <div className="mb-wide rounded-card border border-line bg-black/20 p-soft">
                    <p className="mb-base text-xs text-ink-muted">{t("admin:agentConfigReviewSubmitHint")}</p>
                    <textarea
                      className="mb-base min-h-[72px] w-full rounded-tile border border-line bg-field p-base text-sm text-ink-primary"
                      placeholder={t("admin:agentConfigReviewSummaryPlaceholder")}
                      value={reviewSummary}
                      onChange={(e) => setReviewSummary(e.target.value)}
                    />
                    {reviewError ? (
                      <p className="mb-base text-xs text-red-300">{reviewError}</p>
                    ) : null}
                    <button
                      type="button"
                      disabled={reviewBusy || runIds.length === 0}
                      onClick={() => void onSubmitReview()}
                      className="rounded-tile bg-indigo-700 px-soft py-snug text-xs text-ink-on-fill hover:bg-indigo-600 disabled:opacity-50"
                    >
                      {reviewBusy ? t("admin:agentConfigReviewSubmitting") : t("admin:agentConfigReviewSubmit")}
                    </button>
                    {runIds.length === 0 ? (
                      <p className="mt-base text-meta text-ink-muted">{t("admin:agentConfigReviewNeedsRuns")}</p>
                    ) : null}
                  </div>
                  {report.reviews.length === 0 ? (
                    <p className="text-xs text-ink-muted">{t("admin:agentConfigExperimentNoReviews")}</p>
                  ) : (
                    <ul className="space-y-base">
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
