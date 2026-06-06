import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { ProjectWorkspaceControls } from "./ProjectWorkspaceControls";
import { getPath, setPath } from "./dashboardDataPaths";
import type { ColumnDef } from "./types";

type Row = Record<string, unknown>;

function StatusPill(props: { status: string }) {
  const s = (props.status || "").toLowerCase();
  const cls =
    s === "succeeded"
      ? "bg-emerald-600/30 text-emerald-200 border-emerald-500/40"
      : s === "failed"
        ? "bg-red-600/30 text-red-200 border-red-500/40"
        : s === "running"
          ? "bg-violet-600/30 text-violet-200 border-violet-500/40"
          : "bg-white/10 text-surface-muted border-white/10";
  return (
    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      {props.status || "—"}
    </span>
  );
}

export function ProjectRowDetailDrawer(props: {
  detailRow: Row;
  detailRowId: string;
  onClose: () => void;
  cols: ColumnDef[];
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  enableRunNow: boolean;
  enableWorkspaceLink: boolean;
  readOnly: boolean;
  dashboardId: string | null;
  defaultWorkspaceId?: string;
}) {
  const {
    detailRow,
    detailRowId,
    onClose,
    cols,
    dp,
    setData,
    enableRunNow,
    enableWorkspaceLink,
    readOnly,
    dashboardId,
    defaultWorkspaceId = "",
  } = props;
  const { t } = useTranslation(["dashboard", "errors"]);
  const auth = useAuth();

  const [runNowInstructions, setRunNowInstructions] = useState("");
  const [runNowWorkspaceId, setRunNowWorkspaceId] = useState(defaultWorkspaceId);
  const [runNowBusy, setRunNowBusy] = useState(false);
  const [runNowMsg, setRunNowMsg] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<any[] | null>(null);
  const [recentRunsErr, setRecentRunsErr] = useState<string | null>(null);
  const [recentRunsBusy, setRecentRunsBusy] = useState(false);

  const updateDetailRowFields = (patch: Record<string, unknown>) => {
    setData((d) => {
      const list = [...((getPath(d, dp) as Row[]) || [])];
      const idx = list.findIndex((x) => String((x as any)?.id ?? "") === detailRowId);
      if (idx < 0) return d;
      list[idx] = { ...(list[idx] || {}), ...patch };
      return setPath(d, dp, list);
    });
  };

  useEffect(() => {
    if (!enableRunNow) return;
    const title = String((detailRow as any)?.title ?? "").trim();
    const remote = String((detailRow as any)?.remote_url ?? "").trim();
    const path = String((detailRow as any)?.project_path ?? "").trim();
    const rowWorkspace = String((detailRow as any)?.workspace_id ?? "").trim();
    const lines = [
      `${t("dashboard:project")}: ${title || t("dashboard:untitled")}`,
      remote ? `${t("dashboard:remote")}: ${remote}` : "",
      path ? `${t("dashboard:localPath")}: ${path}` : "",
      "",
      `${t("dashboard:task")}:`,
      "",
    ].filter(Boolean);
    setRunNowInstructions(lines.join("\n"));
    setRunNowWorkspaceId(rowWorkspace || defaultWorkspaceId);
    setRunNowMsg(null);
    setRecentRuns(null);
    setRecentRunsErr(null);
  }, [enableRunNow, detailRow, detailRowId, defaultWorkspaceId, t]);

  const refreshRecentRuns = async () => {
    if (!enableRunNow || !dashboardId) return;
    const pid = String((detailRow as any)?.id ?? "").trim();
    if (!pid) return;
    setRecentRunsBusy(true);
    setRecentRunsErr(null);
    try {
      const q = new URLSearchParams({
        dashboard_id: String(dashboardId),
        project_row_id: pid,
        limit: "10",
      });
      const res = await apiFetch(`/v1/project-runs?${q.toString()}`, auth);
      const j = (await res.json().catch(() => null)) as any;
      if (!res.ok || !j?.ok) {
        setRecentRunsErr(`${t("errors:generic")}: ${String(j?.detail ?? j?.error ?? res.status)}`);
        setRecentRuns(null);
      } else {
        setRecentRuns(Array.isArray(j.runs) ? j.runs : []);
      }
    } catch (e) {
      setRecentRunsErr(`${t("errors:generic")}: ${String(e)}`);
      setRecentRuns(null);
    } finally {
      setRecentRunsBusy(false);
    }
  };

  useEffect(() => {
    if (!enableRunNow) return;
    void refreshRecentRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enableRunNow, detailRowId]);

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/60 p-4">
      <div className="h-full w-full max-w-lg overflow-auto rounded-xl border border-surface-border bg-surface-raised p-4 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-surface-muted">{t("dashboard:project")}</div>
            <div className="text-lg font-semibold text-white">
              {String((detailRow as any).title ?? "").trim() || t("dashboard:untitled")}
            </div>
            <div className="mt-1 text-xs text-surface-muted">id: {detailRowId}</div>
          </div>
          <button
            type="button"
            className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-neutral-100 hover:bg-white/5"
            onClick={onClose}
          >
            {t("dashboard:close")}
          </button>
        </div>

        {enableWorkspaceLink ? (
          <ProjectWorkspaceControls
            auth={auth}
            workspaceId={runNowWorkspaceId}
            remoteUrl={String((detailRow as any)?.remote_url ?? "")}
            readOnly={readOnly}
            onWorkspaceChange={(wid, projectPath) => {
              setRunNowWorkspaceId(wid);
              updateDetailRowFields({
                workspace_id: wid,
                ...(projectPath ? { project_path: projectPath } : {}),
              });
            }}
          />
        ) : null}

        {enableRunNow ? (
          <div className="mb-4 rounded-xl border border-surface-border bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-xs font-medium uppercase tracking-wide text-surface-muted">
                {t("dashboard:runNow")}
              </div>
              <button
                type="button"
                disabled={runNowBusy || !runNowInstructions.trim() || !runNowWorkspaceId.trim()}
                className="rounded-md bg-violet-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={async () => {
                  setRunNowBusy(true);
                  setRunNowMsg(null);
                  try {
                    const res = await apiFetch(`/v1/project-runs`, auth, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        instructions: runNowInstructions,
                        workspace_id: runNowWorkspaceId.trim(),
                        coding_workflow: {},
                        dashboard_id: dashboardId,
                        project_row_id: String((detailRow as any)?.id ?? ""),
                        project_title: String((detailRow as any)?.title ?? ""),
                      }),
                    });
                    const j = (await res.json().catch(() => null)) as any;
                    if (!res.ok || !j?.ok) {
                      setRunNowMsg(
                        `${t("errors:generic")}: ${String(j?.detail ?? j?.error ?? res.status)}`
                      );
                    } else {
                      setRunNowMsg(t("dashboard:queuedRun", { id: String(j.run?.id ?? "") }));
                      void refreshRecentRuns();
                    }
                  } catch (e) {
                    setRunNowMsg(`${t("errors:generic")}: ${String(e)}`);
                  } finally {
                    setRunNowBusy(false);
                  }
                }}
              >
                {runNowBusy ? t("dashboard:queueing") : t("dashboard:queueRun")}
              </button>
            </div>
            {!enableWorkspaceLink ? (
              <label className="mb-2 block text-[11px] text-surface-muted">
                {t("dashboard:workspaceIdUuid")}
                <input
                  value={runNowWorkspaceId}
                  onChange={(e) => setRunNowWorkspaceId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-border bg-black/30 px-3 py-1.5 font-mono text-xs text-neutral-100 outline-none focus:border-violet-400/60"
                  placeholder={t("dashboard:workspaceUuidPlaceholder")}
                />
              </label>
            ) : runNowWorkspaceId ? (
              <p className="mb-2 truncate font-mono text-[10px] text-surface-muted">{runNowWorkspaceId}</p>
            ) : (
              <p className="mb-2 text-xs text-amber-300/90">{t("dashboard:workspaceRequiredForRun")}</p>
            )}
            <textarea
              value={runNowInstructions}
              onChange={(e) => setRunNowInstructions(e.target.value)}
              className="min-h-[110px] w-full resize-y rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-xs text-neutral-100 outline-none focus:border-violet-400/60"
              placeholder={t("dashboard:describeWhatToDo")}
            />
            {runNowMsg ? <div className="mt-2 text-xs text-surface-muted">{runNowMsg}</div> : null}
          </div>
        ) : null}

        {enableRunNow ? (
          <div className="mb-4 rounded-xl border border-surface-border bg-black/10 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-xs font-medium uppercase tracking-wide text-surface-muted">
                {t("dashboard:recentRuns")}
              </div>
              <button
                type="button"
                className="rounded-md border border-surface-border px-2 py-1 text-[11px] text-neutral-100 hover:bg-white/5 disabled:opacity-60"
                disabled={recentRunsBusy}
                onClick={() => void refreshRecentRuns()}
              >
                {recentRunsBusy ? t("dashboard:loading") : t("dashboard:refresh")}
              </button>
            </div>
            {recentRunsErr ? (
              <div className="text-xs text-red-200/90">{recentRunsErr}</div>
            ) : recentRuns && recentRuns.length === 0 ? (
              <div className="text-xs text-surface-muted">{t("dashboard:recentRunsNoneYet")}</div>
            ) : recentRuns ? (
              <div className="space-y-2">
                {recentRuns.map((r) => (
                  <div key={String(r.id)} className="rounded-lg border border-surface-border bg-black/20 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="truncate text-xs text-neutral-100">
                        {String(r.project_title ?? "") || "Run"}
                      </div>
                      <StatusPill status={String(r.status ?? "")} />
                    </div>
                    <div className="mt-1 text-[11px] text-surface-muted">{String(r.created_at ?? "")}</div>
                    {r.error ? (
                      <div className="mt-1 text-[11px] text-red-200/90">{String(r.error)}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-surface-muted">{t("dashboard:runNowLoading")}</div>
            )}
          </div>
        ) : null}

        <div className="grid gap-3">
          {cols
            .filter((c) => c?.field && c.field !== "pinned")
            .map((c) => (
              <div key={String(c.field)}>
                <div className="mb-1 text-xs font-medium uppercase tracking-wide text-surface-muted">
                  {c.label || c.field}
                </div>
                <div className="rounded-lg border border-surface-border bg-black/20 p-2 text-sm text-neutral-100">
                  {String(((detailRow as any) ?? {})[c.field] ?? "").trim() || "—"}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
