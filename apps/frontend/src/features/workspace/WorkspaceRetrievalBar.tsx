import { useCallback, useEffect, useRef, useState } from "react";
import type { AuthContextValue } from "../../auth/AuthContext";
import {
  apiFetch,
  patchWorkspace,
  type WorkspaceApiRecord,
  type WorkspaceIndexJob,
  type WorkspaceIndexStatus,
} from "../../lib/api";

type Props = {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspace: WorkspaceApiRecord | null;
  canEdit: boolean;
  onWorkspaceUpdated: (ws: WorkspaceApiRecord) => void;
  className?: string;
};

function fmtIndexTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "—";
  }
}

function pill(on: boolean) {
  return on
    ? `rounded border border-emerald-500/40 bg-emerald-950/50 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-emerald-200/95`
    : `rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-neutral-500`;
}

function indexJobRunning(job: WorkspaceIndexJob | null | undefined): boolean {
  return job?.status === "running";
}

function indexProgressPct(job: WorkspaceIndexJob | null | undefined): number | null {
  if (!job || job.status !== "running") return null;
  const done = job.files_done;
  const total = job.files_total;
  if (typeof done !== "number" || typeof total !== "number" || total <= 0) return null;
  return Math.min(100, Math.round((done / total) * 100));
}

function indexProgressLabel(job: WorkspaceIndexJob | null | undefined): string {
  if (!job || job.status !== "running") return "";
  const phase = (job.phase || "index").toLowerCase();
  const done = job.files_done ?? 0;
  const total = job.files_total ?? 0;
  const pct = indexProgressPct(job);
  const phaseLabel = phase === "qdrant" ? "embedding" : phase === "scan" ? "scan" : phase;
  if (total > 0 && pct != null) {
    return `Indexing (${phaseLabel})… ${pct}% (${done}/${total})`;
  }
  return `Indexing (${phaseLabel})…`;
}

export function WorkspaceRetrievalBar({
  auth,
  workspace,
  canEdit,
  onWorkspaceUpdated,
  className = "",
}: Props) {
  const [status, setStatus] = useState<WorkspaceIndexStatus | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<"toggle" | "index" | null>(null);
  const [indexing, setIndexing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async () => {
    if (!workspace?.id) {
      setStatus(null);
      return null;
    }
    setStatusErr(null);
    try {
      const r = await apiFetch(
        `/v1/workspaces/${encodeURIComponent(workspace.id)}/index/status`,
        auth
      );
      const j = (await r.json().catch(() => null)) as WorkspaceIndexStatus & {
        detail?: string;
      };
      if (!r.ok || !j?.ok) {
        setStatus(null);
        setStatusErr(String(j?.detail ?? j?.error ?? r.status));
        return null;
      }
      setStatus(j);
      return j;
    } catch (e) {
      setStatus(null);
      setStatusErr(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [auth, workspace?.id]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus, workspace?.semantic_index_enabled, workspace?.retrieval_enabled]);

  useEffect(() => {
    const job = status?.index_job;
    if (indexJobRunning(job)) {
      setIndexing(true);
    } else if (job?.status === "done" || job?.status === "failed") {
      setIndexing(false);
    }
  }, [status?.index_job]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(() => {
      void (async () => {
        const j = await loadStatus();
        const job = j?.index_job;
        if (!indexJobRunning(job)) {
          stopPolling();
          setIndexing(false);
          setBusy(null);
          if (workspace?.id) {
            const list = await apiFetch("/v1/workspaces", auth);
            const lj = (await list.json()) as { workspaces?: WorkspaceApiRecord[] };
            const fresh = (lj.workspaces ?? []).find((w) => w.id === workspace.id);
            if (fresh) onWorkspaceUpdated(fresh);
          }
        }
      })();
    }, 1500);
  }, [auth, loadStatus, onWorkspaceUpdated, stopPolling, workspace?.id]);

  useEffect(() => {
    void (async () => {
      const j = await loadStatus();
      if (indexJobRunning(j?.index_job)) {
        setIndexing(true);
        startPolling();
      }
    })();
    return () => stopPolling();
  }, [loadStatus, startPolling, stopPolling, workspace?.id]);

  const patchFlags = async (patch: {
    semantic_index_enabled?: boolean;
    retrieval_enabled?: boolean;
  }) => {
    if (!workspace?.id || !canEdit) return;
    setBusy("toggle");
    const res = await patchWorkspace(auth, workspace.id, patch);
    setBusy(null);
    if (res.ok) {
      onWorkspaceUpdated(res.workspace);
      void loadStatus();
    } else {
      setStatusErr(res.error);
    }
  };

  const runIndex = async () => {
    if (!workspace?.id || !canEdit) return;
    setBusy("index");
    setIndexing(true);
    setStatusErr(null);
    try {
      const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(workspace.id)}/index`, auth, {
        method: "POST",
        body: JSON.stringify({ max_files: 5000 }),
      });
      const j = (await r.json().catch(() => null)) as {
        ok?: boolean;
        detail?: string;
        status?: WorkspaceIndexStatus;
        job?: WorkspaceIndexJob;
        already_running?: boolean;
      };
      if (!r.ok || !j?.ok) {
        setStatusErr(String(j?.detail ?? r.status));
        setIndexing(false);
        setBusy(null);
        return;
      }
      if (j.status) setStatus(j.status);
      else await loadStatus();
      if (indexJobRunning(j.status?.index_job ?? j.job) || j.already_running) {
        startPolling();
      } else {
        setIndexing(false);
        setBusy(null);
        const list = await apiFetch("/v1/workspaces", auth);
        const lj = (await list.json()) as { workspaces?: WorkspaceApiRecord[] };
        const fresh = (lj.workspaces ?? []).find((w) => w.id === workspace.id);
        if (fresh) onWorkspaceUpdated(fresh);
      }
    } catch (e) {
      setStatusErr(e instanceof Error ? e.message : String(e));
      setIndexing(false);
      setBusy(null);
    }
  };

  if (!workspace) return null;

  const indexOn = workspace.semantic_index_enabled !== false;
  const retrievalOn = workspace.retrieval_enabled !== false;
  const qdrantOk = status?.qdrant?.reachable === true;
  const symbolCount =
    typeof status?.last_index_stats?.total_symbols === "number"
      ? status.last_index_stats.total_symbols
      : null;
  const activeJob = status?.index_job;
  const showProgress = indexing || indexJobRunning(activeJob);
  const progressPct = indexProgressPct(activeJob);
  const progressLabel = indexProgressLabel(activeJob);
  const indexFailed = activeJob?.status === "failed";
  const indexStale =
    status?.index_stale === true ||
    (status?.index_stale_reason != null && status.index_stale_reason !== "");
  const staleReason = status?.index_stale_reason;

  return (
    <div
      className={`rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-[10px] leading-snug text-neutral-300 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-surface-muted">Index</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(indexOn)}
          title={
            canEdit
              ? "Toggle semantic indexing (Qdrant) for this workspace"
              : "Read-only — cannot change"
          }
          onClick={() => void patchFlags({ semantic_index_enabled: !indexOn })}
        >
          {indexOn ? "on" : "off"}
        </button>
        {canEdit ? (
          <button
            type="button"
            disabled={!indexOn || busy === "index" || showProgress}
            className="rounded border border-violet-500/35 bg-violet-950/40 px-1.5 py-0.5 text-[9px] font-medium text-violet-200/95 hover:bg-violet-900/50 disabled:opacity-50"
            title="Run tree-sitter scan + Qdrant upsert"
            onClick={() => void runIndex()}
          >
            {showProgress ? "…" : "Reindex"}
          </button>
        ) : null}
        <span className="text-neutral-600">·</span>
        <span className="font-semibold uppercase tracking-wide text-surface-muted">Retrieval</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(retrievalOn)}
          title={
            canEdit
              ? "Toggle retrieve_context bundle for this workspace"
              : "Read-only — cannot change"
          }
          onClick={() => void patchFlags({ retrieval_enabled: !retrievalOn })}
        >
          {retrievalOn ? "on" : "off"}
        </button>
      </div>
      {showProgress ? (
        <div
          className="mt-1.5 space-y-1"
          title={progressLabel || "Indexing in progress"}
        >
          <div className="flex items-center justify-between gap-2 text-[9px] text-violet-200/90">
            <span className="truncate">{progressLabel || "Indexing…"}</span>
            {progressPct != null ? <span className="shrink-0 tabular-nums">{progressPct}%</span> : null}
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-violet-500/70 transition-[width] duration-300"
              style={{ width: progressPct != null ? `${progressPct}%` : "30%" }}
            />
          </div>
        </div>
      ) : indexFailed && activeJob?.error ? (
        <p className="mt-1 text-[9px] text-amber-300/90" title={activeJob.error}>
          Index failed: {activeJob.error.slice(0, 120)}
        </p>
      ) : null}
      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-neutral-500">
        <span title="Last successful index run">
          Indexed: {fmtIndexTime(status?.last_index_at ?? workspace.last_index_at)}
        </span>
        {symbolCount != null ? <span>· {symbolCount} symbols</span> : null}
        {indexOn && indexStale ? (
          <span
            className="text-amber-300/95"
            title={
              staleReason === "never_indexed"
                ? "No semantic index yet — run Reindex"
                : "Git has commits newer than the last index — Reindex recommended"
            }
          >
            · stale
          </span>
        ) : null}
        <span>
          · Qdrant{" "}
          {status?.qdrant?.configured === false
            ? "n/a"
            : qdrantOk
              ? "ok"
              : status?.qdrant?.reachable === false
                ? "down"
                : "—"}
        </span>
        {workspace.last_index_error ? (
          <span className="text-amber-300/90" title={workspace.last_index_error}>
            · err
          </span>
        ) : null}
        {statusErr ? <span className="text-red-400/90">· {statusErr}</span> : null}
      </div>
    </div>
  );
}
