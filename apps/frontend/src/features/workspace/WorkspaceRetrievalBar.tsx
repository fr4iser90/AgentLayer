import { useCallback, useEffect, useState } from "react";
import type { AuthContextValue } from "../../auth/AuthContext";
import {
  apiFetch,
  patchWorkspace,
  type WorkspaceApiRecord,
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

function pill(on: boolean, onLabel: string, offLabel: string) {
  return on
    ? `rounded border border-emerald-500/40 bg-emerald-950/50 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-emerald-200/95`
    : `rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-neutral-500`;
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

  const loadStatus = useCallback(async () => {
    if (!workspace?.id) {
      setStatus(null);
      return;
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
        return;
      }
      setStatus(j);
    } catch (e) {
      setStatus(null);
      setStatusErr(e instanceof Error ? e.message : String(e));
    }
  }, [auth, workspace?.id]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus, workspace?.semantic_index_enabled, workspace?.retrieval_enabled]);

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
      };
      if (!r.ok || !j?.ok) {
        setStatusErr(String(j?.detail ?? r.status));
      } else if (j.status) {
        setStatus(j.status);
      } else {
        await loadStatus();
      }
      const list = await apiFetch("/v1/workspaces", auth);
      const lj = (await list.json()) as { workspaces?: WorkspaceApiRecord[] };
      const fresh = (lj.workspaces ?? []).find((w) => w.id === workspace.id);
      if (fresh) onWorkspaceUpdated(fresh);
    } catch (e) {
      setStatusErr(e instanceof Error ? e.message : String(e));
    } finally {
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

  return (
    <div
      className={`rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-[10px] leading-snug text-neutral-300 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-surface-muted">Index</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(indexOn, "on", "off")}
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
            disabled={!indexOn || busy === "index"}
            className="rounded border border-violet-500/35 bg-violet-950/40 px-1.5 py-0.5 text-[9px] font-medium text-violet-200/95 hover:bg-violet-900/50 disabled:opacity-50"
            title="Run tree-sitter scan + Qdrant upsert"
            onClick={() => void runIndex()}
          >
            {busy === "index" ? "…" : "Reindex"}
          </button>
        ) : null}
        <span className="text-neutral-600">·</span>
        <span className="font-semibold uppercase tracking-wide text-surface-muted">Retrieval</span>
        <button
          type="button"
          disabled={!canEdit || busy !== null}
          className={pill(retrievalOn, "on", "off")}
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
      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-neutral-500">
        <span title="Last successful index run">
          Indexed: {fmtIndexTime(status?.last_index_at ?? workspace.last_index_at)}
        </span>
        {symbolCount != null ? <span>· {symbolCount} symbols</span> : null}
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
