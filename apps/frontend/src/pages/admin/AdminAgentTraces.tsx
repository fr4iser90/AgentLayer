import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  fetchAdminRuns,
  fetchAdminRunTrace,
  type RunTrace,
} from "../../lib/runTracesApi";

export function AdminAgentTraces() {
  const auth = useAuth();
  const [runs, setRuns] = useState<RunTrace[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
      setError(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

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
        setError(e instanceof Error ? e.message : "Failed to load trace");
      }
    })();
  }, [auth, selectedId]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden p-4">
      <div className="flex shrink-0 items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-white">Agent traces</h1>
          <p className="text-sm text-surface-muted">
            Persisted runs and correlated tool invocations (debug / operator).
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns()}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10"
        >
          Refresh
        </button>
      </div>
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      <div className="flex min-h-0 flex-1 gap-4 overflow-hidden">
        <div className="flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border border-surface-border bg-surface-raised/40">
          <div className="border-b border-white/5 px-3 py-2 text-xs font-medium uppercase tracking-wide text-surface-muted">
            Recent runs
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto p-2 text-sm">
            {loading ? (
              <li className="text-surface-muted">Loading…</li>
            ) : runs.length === 0 ? (
              <li className="text-surface-muted">No runs yet.</li>
            ) : (
              runs.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(r.id)}
                    className={[
                      "w-full rounded-lg px-2 py-1.5 text-left",
                      selectedId === r.id ? "bg-indigo-500/20 text-white" : "text-neutral-300 hover:bg-white/5",
                    ].join(" ")}
                  >
                    <span className="font-mono text-[10px] text-surface-muted">{r.id.slice(0, 8)}…</span>
                    <span className="ml-1">{r.agent_id ?? "—"}</span>
                    <span className="ml-1 text-xs text-surface-muted">{r.status}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-xl border border-surface-border bg-black/30 p-4">
          {!selectedId || !detail ? (
            <p className="text-sm text-surface-muted">Select a run to inspect tools and child runs.</p>
          ) : (
            <div className="space-y-4 text-sm">
              <pre className="overflow-x-auto rounded-lg bg-black/50 p-3 text-xs text-neutral-300">
                {JSON.stringify(detail.run, null, 2)}
              </pre>
              {detail.child_runs.length > 0 ? (
                <section>
                  <h2 className="mb-2 text-xs font-semibold uppercase text-surface-muted">Child runs</h2>
                  <ul className="space-y-1 font-mono text-xs text-indigo-200/90">
                    {detail.child_runs.map((c) => (
                      <li key={c.id}>
                        {c.id} — {c.agent_id} ({c.status})
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              <section>
                <h2 className="mb-2 text-xs font-semibold uppercase text-surface-muted">
                  Tool invocations ({detail.tool_invocations.length})
                </h2>
                <ul className="space-y-2">
                  {detail.tool_invocations.map((t) => (
                    <li
                      key={String(t.id)}
                      className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                    >
                      <span className="font-medium text-sky-300">{String(t.tool_name)}</span>
                      <span className={t.ok ? " text-emerald-400" : " text-red-400"}>
                        {t.ok ? " ok" : " err"}
                      </span>
                      <pre className="mt-1 max-h-24 overflow-auto text-[10px] text-neutral-500">
                        {JSON.stringify(t.args_json, null, 2)}
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
