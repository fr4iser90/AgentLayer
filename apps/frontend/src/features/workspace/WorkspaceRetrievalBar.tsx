import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import {
  apiFetch,
  patchWorkspace,
  type WorkspaceApiRecord,
  type WorkspaceIndexJob,
  type WorkspaceIndexMode,
  type WorkspaceIndexStatus,
} from "../../lib/api";
import type { IndexActivityEvent } from "../chat/indexActivity";

type Props = {
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspace: WorkspaceApiRecord | null;
  canEdit: boolean;
  onWorkspaceUpdated: (ws: WorkspaceApiRecord) => void;
  /** Emit index run lifecycle for chat run cards (optional). */
  onIndexActivity?: (ev: IndexActivityEvent) => void;
  className?: string;
};

function fmtIndexTime(iso: string | null | undefined, t: (key: string) => string): string {
  if (!iso) return t("workspace:never");
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

const PHASE_LABELS: Record<string, string> = {
  scan: "scan",
  qdrant: "embed",
  neo4j: "graph",
  docs_rag: "docs",
  incremental: "incr",
  starting: "start",
};

function indexProgressLabel(job: WorkspaceIndexJob | null | undefined, t: (key: string, opts?: any) => string): string {
  if (!job || job.status !== "running") return "";
  const phase = (job.phase || "index").toLowerCase();
  const done = job.files_done ?? 0;
  const total = job.files_total ?? 0;
  const pct = indexProgressPct(job);
  const phaseLabel = PHASE_LABELS[phase] ?? phase;
  if (total > 0 && pct != null) {
    return t("workspace:indexingWithPct", { phase: phaseLabel, pct, done, total });
  }
  return t("workspace:indexing", { phase: phaseLabel });
}

const INDEX_BTN =
  "rounded border px-1.5 py-0.5 text-[9px] font-medium disabled:opacity-50";

export function WorkspaceRetrievalBar({
  auth,
  workspace,
  canEdit,
  onWorkspaceUpdated,
  onIndexActivity,
  className = "",
}: Props) {
  const { t } = useTranslation(["workspace", "common"]);
  const [status, setStatus] = useState<WorkspaceIndexStatus | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<"toggle" | WorkspaceIndexMode | null>(null);
  const [indexing, setIndexing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const indexRunStartedAtRef = useRef<number | null>(null);
  const indexRunModeRef = useRef<WorkspaceIndexMode | null>(null);

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
  }, [loadStatus, workspace?.semantic_index_enabled, workspace?.retrieval_enabled, workspace?.docs_rag_enabled]);

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

  const finishIndexRun = useCallback(
    (mode: WorkspaceIndexMode, job: WorkspaceIndexJob | null | undefined, failed: boolean) => {
      const started = indexRunStartedAtRef.current;
      indexRunStartedAtRef.current = null;
      indexRunModeRef.current = null;
      onIndexActivity?.({
        type: "done",
        mode,
        failed,
        error: job?.error ?? undefined,
        durationMs: started != null ? Date.now() - started : undefined,
        filesDone: job?.files_done ?? undefined,
        filesTotal: job?.files_total ?? undefined,
        phase: job?.phase ?? undefined,
      });
    },
    [onIndexActivity]
  );

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
          const mode = indexRunModeRef.current;
          if (mode) {
            finishIndexRun(mode, job, job?.status === "failed");
          }
          if (workspace?.id) {
            const list = await apiFetch("/v1/workspaces", auth);
            const lj = (await list.json()) as { workspaces?: WorkspaceApiRecord[] };
            const fresh = (lj.workspaces ?? []).find((w) => w.id === workspace.id);
            if (fresh) onWorkspaceUpdated(fresh);
          }
        }
      })();
    }, 1500);
  }, [auth, finishIndexRun, loadStatus, onWorkspaceUpdated, stopPolling, workspace?.id]);

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
    docs_rag_enabled?: boolean;
    graph_index_enabled?: boolean;
    index_on_write?: string | null;
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

  const runIndex = async (mode: WorkspaceIndexMode) => {
    if (!workspace?.id || !canEdit) return;
    setBusy(mode);
    setIndexing(true);
    setStatusErr(null);
    indexRunStartedAtRef.current = Date.now();
    indexRunModeRef.current = mode;
    onIndexActivity?.({ type: "start", mode });
    try {
      const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(workspace.id)}/index`, auth, {
        method: "POST",
        body: JSON.stringify({ max_files: 5000, mode }),
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
        finishIndexRun(mode, null, true);
        return;
      }
      if (j.status) setStatus(j.status);
      else await loadStatus();
      if (indexJobRunning(j.status?.index_job ?? j.job) || j.already_running) {
        startPolling();
      } else {
        setIndexing(false);
        setBusy(null);
        finishIndexRun(mode, j.status?.index_job ?? j.job ?? null, false);
        const list = await apiFetch("/v1/workspaces", auth);
        const lj = (await list.json()) as { workspaces?: WorkspaceApiRecord[] };
        const fresh = (lj.workspaces ?? []).find((w) => w.id === workspace.id);
        if (fresh) onWorkspaceUpdated(fresh);
      }
    } catch (e) {
      setStatusErr(e instanceof Error ? e.message : String(e));
      setIndexing(false);
      setBusy(null);
      finishIndexRun(mode, null, true);
    }
  };

  if (!workspace) return null;

  const indexOn = workspace.semantic_index_enabled !== false;
  const retrievalOn = workspace.retrieval_enabled !== false;
  const docsRagOn = workspace.docs_rag_enabled !== false;
  const graphOn = workspace.graph_index_enabled !== false;
  const indexOnWriteEffective =
    status?.index_on_write_effective ?? workspace.index_on_write ?? "debounced";
  const filesOutOfDate =
    typeof status?.files_out_of_date === "number" ? status.files_out_of_date : null;
  const qdrantOk = status?.qdrant?.reachable === true;
  const neo4jOk = status?.neo4j?.reachable === true;
  const symbolCount =
    typeof status?.last_index_stats?.total_symbols === "number"
      ? status.last_index_stats.total_symbols
      : null;
  const graphEdges =
    typeof status?.last_index_stats?.neo4j_edges === "number"
      ? status.last_index_stats.neo4j_edges
      : null;
  const activeJob = status?.index_job;
  const showProgress = indexing || indexJobRunning(activeJob);
  const progressPct = indexProgressPct(activeJob);
  const progressLabel = indexProgressLabel(activeJob, t);
  const indexFailed = activeJob?.status === "failed";
  const indexStale =
    status?.index_stale === true ||
    (status?.index_stale_reason != null && status.index_stale_reason !== "");
  const staleReason = status?.index_stale_reason;
  const indexBusy = busy !== null && busy !== "toggle";

  return (
    <div
      className={`rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-[10px] leading-snug text-neutral-300 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:codeIndex")}</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(indexOn)}
          title={
            canEdit
              ? t("workspace:treeSitterHint")
              : t("workspace:readOnlyCannotChange")
          }
          onClick={() => void patchFlags({ semantic_index_enabled: !indexOn })}
        >
          {indexOn ? t("common:on") : t("common:off")}
        </button>
        <span className="text-neutral-600">·</span>
        <span className="font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:retrieval")}</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(retrievalOn)}
          title={
            canEdit
              ? t("workspace:toggleRetrievalHint")
              : t("workspace:readOnlyCannotChange")
          }
          onClick={() => void patchFlags({ retrieval_enabled: !retrievalOn })}
        >
          {retrievalOn ? t("common:on") : t("common:off")}
        </button>
        <span className="text-neutral-600">·</span>
        <span className="font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:docsRag")}</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(docsRagOn)}
          title={
            canEdit
              ? t("workspace:docsIndexHint")
              : t("workspace:readOnlyCannotChange")
          }
          onClick={() => void patchFlags({ docs_rag_enabled: !docsRagOn })}
        >
          {docsRagOn ? t("common:on") : t("common:off")}
        </button>
        <span className="text-neutral-600">·</span>
        <span className="font-semibold uppercase tracking-wide text-surface-muted">Graph</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(graphOn)}
          title="Neo4j call-graph index (coding_graph)"
          onClick={() => void patchFlags({ graph_index_enabled: !graphOn })}
        >
          {graphOn ? t("common:on") : t("common:off")}
        </button>
      </div>

      {canEdit ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <label className="text-[9px] text-surface-muted" htmlFor={`idx-write-${workspace.id}`}>
            Index on write
          </label>
          <select
            id={`idx-write-${workspace.id}`}
            className="rounded border border-white/15 bg-black/40 px-1.5 py-0.5 text-[9px] text-neutral-200"
            disabled={busy !== null}
            value={workspace.index_on_write ?? ""}
            title={`Effective: ${indexOnWriteEffective}`}
            onChange={(e) => {
              const v = e.target.value;
              void patchFlags({ index_on_write: v === "" ? null : v });
            }}
          >
            <option value="">operator default ({indexOnWriteEffective})</option>
            <option value="debounced">debounced</option>
            <option value="immediate">immediate</option>
            <option value="off">off</option>
          </select>
        </div>
      ) : null}

      {canEdit ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="mr-0.5 text-[9px] uppercase tracking-wide text-surface-muted">{t("workspace:reindex")}</span>
          <button
            type="button"
            disabled={!indexOn || indexBusy || showProgress}
            className={`${INDEX_BTN} border-violet-500/35 bg-violet-950/40 text-violet-200/95 hover:bg-violet-900/50`}
            title={t("workspace:reindexAllTitle")}
            onClick={() => void runIndex("full")}
          >
            {busy === "full" && showProgress ? "…" : t("workspace:all")}
          </button>
          <button
            type="button"
            disabled={!indexOn || indexBusy || showProgress}
            className={`${INDEX_BTN} border-sky-500/35 bg-sky-950/40 text-sky-200/95 hover:bg-sky-900/50`}
            title={t("workspace:reindexCodeTitle")}
            onClick={() => void runIndex("code")}
          >
            {busy === "code" && showProgress ? "…" : t("workspace:code")}
          </button>
          <button
            type="button"
            disabled={!docsRagOn || indexBusy || showProgress}
            className={`${INDEX_BTN} border-amber-500/35 bg-amber-950/40 text-amber-200/95 hover:bg-amber-900/50`}
            title={t("workspace:reindexDocsTitle")}
            onClick={() => void runIndex("docs")}
          >
            {busy === "docs" && showProgress ? "…" : t("workspace:docs")}
          </button>
        </div>
      ) : null}

      {showProgress ? (
        <div className="mt-1.5 space-y-1" title={progressLabel || t("workspace:indexingInProgress")}>
          <div className="flex items-center justify-between gap-2 text-[9px] text-violet-200/90">
            <span className="truncate">{progressLabel || t("workspace:indexingEllipsis")}</span>
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
          {t("workspace:indexFailed", { err: activeJob.error.slice(0, 120) })}
        </p>
      ) : null}

      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-neutral-500">
        <span title={t("workspace:lastCodeIndexRun")}>
          {t("workspace:code")}: {fmtIndexTime(status?.last_index_at ?? workspace.last_index_at, t)}
        </span>
        {symbolCount != null ? <span>· {symbolCount} symbols</span> : null}
        {graphEdges != null && graphEdges > 0 ? <span>· {graphEdges} graph edges</span> : null}
        {typeof status?.last_docs_rag_stats?.files_ingested === "number" ? (
          <span>· {status.last_docs_rag_stats.files_ingested} md files</span>
        ) : typeof workspace.last_docs_rag_stats?.files_ingested === "number" ? (
          <span>· {workspace.last_docs_rag_stats.files_ingested} md files</span>
        ) : null}
        <span title={t("workspace:workspaceMarkdownRag")}>
          · {t("workspace:docs")}: {fmtIndexTime(status?.last_docs_rag_at ?? workspace.last_docs_rag_at, t)}
        </span>
        {indexOn && indexStale ? (
          <span
            className="text-amber-300/95"
            title={
              staleReason === "never_indexed"
                ? t("workspace:noCodeIndexYet")
                : staleReason === "files_changed_since_index"
                  ? `${filesOutOfDate ?? "?"} file(s) changed since index`
                  : t("workspace:gitNewerThanIndex")
            }
          >
            · {t("workspace:stale")}
            {staleReason === "files_changed_since_index" && filesOutOfDate != null
              ? ` (${filesOutOfDate})`
              : ""}
          </span>
        ) : null}
        <span>
          · Qdrant{" "}
          {status?.qdrant?.configured === false
            ? t("workspace:na")
            : qdrantOk
              ? t("workspace:ok")
              : status?.qdrant?.reachable === false
                ? t("workspace:down")
                : "—"}
        </span>
        <span>
          · Neo4j{" "}
          {status?.neo4j?.configured === false
            ? t("workspace:na")
            : neo4jOk
              ? t("workspace:ok")
              : status?.neo4j?.reachable === false
                ? t("workspace:down")
                : "—"}
        </span>
        {workspace.last_index_error ? (
          <span className="text-amber-300/90" title={workspace.last_index_error}>
            · {t("workspace:err")}
          </span>
        ) : null}
        {statusErr ? <span className="text-red-400/90">· {statusErr}</span> : null}
      </div>
    </div>
  );
}
