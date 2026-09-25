import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  fetchAdminRuns,
  fetchAdminRunTrace,
  type RunTrace,
} from "../../lib/runTracesApi";

export function AdminAgentTraces() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const runFromUrl = searchParams.get("run");
  const [runs, setRuns] = useState<RunTrace[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(runFromUrl);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof fetchAdminRunTrace>> | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchAdminRuns(auth);
      setRuns(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:agentTracesFailedLoadRuns"));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (runFromUrl) setSelectedId(runFromUrl);
  }, [runFromUrl]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void (async () => {
      try {
        const d = await fetchAdminRunTrace(auth, selectedId);
        setDetail(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("admin:agentTracesFailedLoadTrace"));
      }
    })();
  }, [auth, selectedId]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-wide overflow-hidden p-wide">
      <div className="flex shrink-0 items-center justify-between gap-base">
        <div>
          <h1 className="text-lg font-semibold text-ink-primary">{t("admin:agentTracesTitle")}</h1>
          <p className="text-sm text-ink-muted">
            {t("admin:agentTracesSubtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns()}
          className="rounded-card border border-line bg-white/5 px-soft py-snug text-sm text-ink-primary hover:bg-white/10"
        >
          {t("admin:agentTracesRefresh")}
        </button>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <div className="flex min-h-0 flex-1 gap-wide overflow-hidden">
        <div className="flex w-72 shrink-0 flex-col overflow-hidden rounded-sheet border border-line bg-card">
          <div className="border-b border-line-subtle px-soft py-base text-xs font-medium uppercase tracking-wide text-ink-muted">
            {t("admin:agentTracesRecentRuns")}
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto p-base text-sm">
            {loading ? (
              <li className="text-ink-muted">{t("admin:agentTracesLoadingRuns")}</li>
            ) : runs.length === 0 ? (
              <li className="text-ink-muted">{t("admin:agentTracesNoneYet")}</li>
            ) : (
              runs.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(r.id)}
                    className={[
                      "w-full rounded-card px-base py-snug text-left",
                      selectedId === r.id ? "bg-accent-subtle text-ink-primary" : "text-ink-secondary hover:bg-white/5",
                    ].join(" ")}
                  >
                    <span className="font-mono text-meta text-ink-muted">{r.id.slice(0, 8)}…</span>
                    <span className="ml-tight">{r.agent_id ?? "—"}</span>
                    <span className="ml-tight text-xs text-ink-muted">{r.status}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-sheet border border-line bg-black/30 p-wide">
          {!selectedId || !detail ? (
            <p className="text-sm text-ink-muted">{t("admin:agentTracesSelectHint")}</p>
          ) : (
            <div className="space-y-wide text-sm">
              <pre className="overflow-x-auto rounded-card bg-black/50 p-soft text-xs text-ink-secondary">
                {JSON.stringify(detail.run, null, 2)}
              </pre>
              {detail.child_runs.length > 0 ? (
                <section>
                  <h2 className="mb-base text-xs font-semibold uppercase text-ink-muted">
                    {t("admin:agentTracesChildRuns")}
                  </h2>
                  <ul className="space-y-tight font-mono text-xs text-badge-accent/90">
                    {detail.child_runs.map((c) => (
                      <li key={c.id}>
                        {c.id} — {c.agent_id} ({c.status})
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              <section>
                <h2 className="mb-base text-xs font-semibold uppercase text-ink-muted">
                  {t("admin:agentTracesToolInvocations", { count: detail.tool_invocations.length })}
                </h2>
                <ul className="space-y-base">
                  {detail.tool_invocations.map((inv) => (
                    <li
                      key={String(inv.id)}
                      className="rounded-card border border-line-subtle bg-white/[0.02] px-soft py-base"
                    >
                      <span className="font-medium text-badge-accent">{String(inv.tool_name)}</span>
                      <span className={inv.ok ? " text-success" : " text-danger"}>
                        {inv.ok ? ` ${t("admin:agentTracesOk")}` : ` ${t("admin:agentTracesErr")}`}
                      </span>
                      <pre className="mt-tight max-h-24 overflow-auto text-meta text-ink-muted">
                        {JSON.stringify(inv.args_json, null, 2)}
                      </pre>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
