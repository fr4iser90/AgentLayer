import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { Badge, type BadgeTone } from "../../ui/Badge";
import { Drawer } from "../../ui/Drawer";
import { ProjectWorkspaceControls } from "./ProjectWorkspaceControls";
import { getPath, setPath } from "./dashboardDataPaths";
import type { ColumnDef } from "./types";
import { TextArea, TextInput } from "../../ui/Field";
import { Button } from "../../ui/Button";

type Row = Record<string, unknown>;

function StatusPill(props: { status: string }) {
  const s = (props.status || "").toLowerCase();
  const tone: BadgeTone =
    s === "succeeded"
      ? "success"
      : s === "failed"
        ? "danger"
        : s === "running"
          ? "accent"
          : "neutral";
  return (
    <Badge tone={tone} className="shrink-0 uppercase">
      {props.status || "—"}
    </Badge>
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
    <Drawer
      open
      onClose={onClose}
      title={String((detailRow as any).title ?? "").trim() || t("dashboard:untitled")}
      headerExtra={
        <>
          <p className="text-meta uppercase tracking-wide text-ink-muted">
            {t("dashboard:project")}
          </p>
          <p className="mt-hair font-mono text-meta text-ink-muted">id: {detailRowId}</p>
        </>
      }
    >

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
          <div className="mb-wide rounded-sheet border border-line bg-black/20 p-soft">
            <div className="mb-base flex items-center justify-between gap-base">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                {t("dashboard:runNow")}
              </div>
              <Button
                variant="ghost"
                size="sm"
                type="button"
                disabled={runNowBusy || !runNowInstructions.trim() || !runNowWorkspaceId.trim()}
                className="bg-violet-600/80 px-soft py-snug text-xs hover:bg-violet-500"
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
              </Button>
            </div>
            {!enableWorkspaceLink ? (
              <label className="mb-base block text-meta text-ink-muted">
                {t("dashboard:workspaceIdUuid")}
                <TextInput
                  mono
                  value={runNowWorkspaceId}
                  onChange={(e) => setRunNowWorkspaceId(e.target.value)}
                  className="mt-tight text-xs outline-none"
                  placeholder={t("dashboard:workspaceUuidPlaceholder")}
                />
              </label>
            ) : runNowWorkspaceId ? (
              <p className="mb-base truncate font-mono text-meta text-ink-muted">{runNowWorkspaceId}</p>
            ) : (
              <p className="mb-base text-xs text-badge-warning">{t("dashboard:workspaceRequiredForRun")}</p>
            )}
            <TextArea
              value={runNowInstructions}
              onChange={(e) => setRunNowInstructions(e.target.value)}
              className="min-h-[110px] resize-y text-xs outline-none"
              placeholder={t("dashboard:describeWhatToDo")}
            />
            {runNowMsg ? <div className="mt-base text-xs text-ink-muted">{runNowMsg}</div> : null}
          </div>
        ) : null}

        {enableRunNow ? (
          <div className="mb-wide rounded-sheet border border-line bg-black/10 p-soft">
            <div className="mb-base flex items-center justify-between gap-base">
              <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                {t("dashboard:recentRuns")}
              </div>
              <Button
                type="button"
                className="px-base py-tight text-meta hover:bg-white/5"
                disabled={recentRunsBusy}
                onClick={() => void refreshRecentRuns()}
              >
                {recentRunsBusy ? t("dashboard:loading") : t("dashboard:refresh")}
              </Button>
            </div>
            {recentRunsErr ? (
              <div className="text-xs text-badge-danger">{recentRunsErr}</div>
            ) : recentRuns && recentRuns.length === 0 ? (
              <div className="text-xs text-ink-muted">{t("dashboard:recentRunsNoneYet")}</div>
            ) : recentRuns ? (
              <div className="space-y-base">
                {recentRuns.map((r) => (
                  <div key={String(r.id)} className="rounded-card border border-line bg-black/20 p-base">
                    <div className="flex items-center justify-between gap-base">
                      <div className="truncate text-xs text-ink-primary">
                        {String(r.project_title ?? "") || "Run"}
                      </div>
                      <StatusPill status={String(r.status ?? "")} />
                    </div>
                    <div className="mt-tight text-meta text-ink-muted">{String(r.created_at ?? "")}</div>
                    {r.error ? (
                      <div className="mt-tight text-meta text-badge-danger">{String(r.error)}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-ink-muted">{t("dashboard:runNowLoading")}</div>
            )}
          </div>
        ) : null}

        <div className="grid gap-soft">
          {cols
            .filter((c) => c?.field && c.field !== "pinned")
            .map((c) => (
              <div key={String(c.field)}>
                <div className="mb-tight text-xs font-medium uppercase tracking-wide text-ink-muted">
                  {c.label || c.field}
                </div>
                <div className="rounded-card border border-line bg-black/20 p-base text-sm text-ink-primary">
                  {String(((detailRow as any) ?? {})[c.field] ?? "").trim() || "—"}
                </div>
              </div>
            ))}
        </div>
    </Drawer>
  );
}
