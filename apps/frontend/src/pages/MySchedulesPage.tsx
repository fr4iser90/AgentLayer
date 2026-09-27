import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, type WorkspaceApiRecord } from "../lib/api";
import { formatDateTimeLocal } from "../lib/formatDateTime";
import {
  EXECUTION_GENERAL,
  type ExecutionTargetCatalogRow,
  executionTargetRequiresWorkspace,
  labelForExecutionTarget,
  normalizeExecutionTargetInput,
} from "../lib/schedulerExecutionTarget";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { Badge, type BadgeTone } from "../ui/Badge";
import { EmptyState } from "../ui/EmptyState";
import { Select, TextArea, TextInput } from "../ui/Field";
import { Checkbox } from "../ui/Checkbox";
import { SkeletonRows } from "../ui/Skeleton";
import { Table, type TableColumn } from "../ui/Table";

type SchedulerJobRow = {
  id: string;
  dashboard_id: string | null;
  execution_target: string;
  title: string | null;
  interval_minutes: number;
  enabled: boolean;
  last_run_at: string | null;
  deleted_at?: string | null;
  created_at: string;
  coding_workflow?: unknown;
  instructions?: string;
};

type SchedulerJobRunSummary = {
  tools?: Array<{ round?: number; name?: string; ok?: boolean; args?: Record<string, unknown>; error?: string }>;
  files_changed?: Array<{ path?: string; stat?: string }>;
  git?: { branch?: string | null; has_changes?: boolean };
  outcome?: string;
  final_reply_excerpt?: string;
  tool_count?: number;
  duration_ms?: number;
};

type SchedulerJobRun = {
  id: string;
  scheduler_job_id: string;
  status: "running" | "succeeded" | "partial" | "failed";
  error: string | null;
  summary_json: SchedulerJobRunSummary;
  started_at: string;
  finished_at: string | null;
};

function runStatusPill(status: SchedulerJobRun["status"]): BadgeTone {
  switch (status) {
    case "succeeded":
      return "success";
    case "partial":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "accent";
  }
}

type CodingWorkflowPreset = {
  agent_id?: "coding" | "coding_plan";
  prompt_preamble?: string;
};

type SchedulerJobPreset = {
  id: string;
  label: string;
  description?: string;
  job: {
    execution_target?: string;
    interval_minutes?: number;
    enabled?: boolean;
    title?: string | null;
    instructions?: string;
    dashboard_id?: string | null;
    coding_workflow?: CodingWorkflowPreset;
  };
};

/** The admin list's owner filter, mirroring `GET /v1/admin/scheduler-jobs`. */
type JobOwnerScope = "all" | "global_only" | "dashboard";

function pill(enabled: boolean): BadgeTone {
  return enabled ? "success" : "neutral";
}

export type SchedulesScope = "user" | "admin";

/**
 * One schedules surface, read through one of two endpoint families.
 *
 * `/schedules` lists the signed-in user's own jobs on
 * `/v1/user/scheduler-jobs`; `/admin/schedules` lists the company's on
 * `/v1/admin/scheduler-jobs`, the family gated by `schedule.manage` on the
 * server. Only the list, who may archive a job, and which rows the filters can
 * reach differ — everything else (create, edit, enable, run history) was the
 * same dialog written twice, so the admin half lives here as a scope instead of
 * a second file that has to be taught every change twice.
 *
 * The create defaults stay split on purpose: a self-service job is born
 * disabled at a daily interval so nobody's agent starts running before they
 * saved it deliberately, while an admin job gets the worker's own default — a
 * hourly row that starts enabled.
 */
export function MySchedulesPage({ scope = "user" }: { scope?: SchedulesScope }) {
  const admin = scope === "admin";
  const jobsPath = admin ? "/v1/admin/scheduler-jobs" : "/v1/user/scheduler-jobs";
  const { t } = useTranslation(["settings", "admin"]);
  const auth = useAuth();
  const [jobs, setJobs] = useState<SchedulerJobRow[] | null>(null);
  const [presets, setPresets] = useState<SchedulerJobPreset[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [scopeFilter, setScopeFilter] = useState<JobOwnerScope>("all");
  const [dashboardId, setDashboardId] = useState("");
  const [includeGlobal, setIncludeGlobal] = useState(true);
  const [targetFilter, setTargetFilter] = useState<"all" | string>("all");
  const [enabledFilter, setEnabledFilter] = useState<"all" | "true" | "false">("all");
  const [includeArchived, setIncludeArchived] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createPresetId, setCreatePresetId] = useState<string>("");
  const [targetCatalog, setTargetCatalog] = useState<ExecutionTargetCatalogRow[]>([]);
  const [createTarget, setCreateTarget] = useState(EXECUTION_GENERAL);
  const [createWorkspaceId, setCreateWorkspaceId] = useState("");
  const [createInterval, setCreateInterval] = useState(admin ? 60 : 1440);
  const [createEnabled, setCreateEnabled] = useState(admin);
  const [createTitle, setCreateTitle] = useState("");
  const [createInstructions, setCreateInstructions] = useState("");
  const [createDashboardId, setCreateDashboardId] = useState("");
  const [createCodingWorkflow, setCreateCodingWorkflow] = useState<CodingWorkflowPreset>({});
  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [workspacesLoading, setWorkspacesLoading] = useState(false);

  const [editJob, setEditJob] = useState<SchedulerJobRow | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editInstructions, setEditInstructions] = useState("");
  const [editInterval, setEditInterval] = useState<number>(60);

  const [runsJob, setRunsJob] = useState<SchedulerJobRow | null>(null);
  const [runs, setRuns] = useState<SchedulerJobRun[] | null>(null);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsErr, setRunsErr] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<SchedulerJobRun | null>(null);

  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (admin) {
      if (scopeFilter === "global_only") {
        q.set("include_global", "true");
      } else if (scopeFilter === "dashboard") {
        if (dashboardId.trim()) q.set("dashboard_id", dashboardId.trim());
        q.set("include_global", includeGlobal ? "true" : "false");
      }
      if (targetFilter !== "all") q.set("execution_target", targetFilter);
      if (enabledFilter !== "all") q.set("enabled", enabledFilter);
      if (includeArchived) q.set("include_archived", "true");
    }
    q.set("limit", "200");
    return q;
  }, [admin, scopeFilter, dashboardId, includeGlobal, targetFilter, enabledFilter, includeArchived]);

  // `min_role: "admin"` in the catalog is decided server-side by
  // `agent_effective_role()`, which reads the `user_site_admin()` flag and only
  // falls back to the legacy `users.role` column when that lookup has no value.
  // Mirroring it here keeps the picker from offering a target the run would
  // refuse — and from hiding one the flag already grants a site admin.
  const elevated =
    auth.user?.site_role === "site_admin" ||
    (!auth.user?.site_role && auth.user?.role === "admin");

  const createTargetOptions = useMemo(
    () =>
      targetCatalog.filter((o) => {
        const role = (o.min_role || "user").toLowerCase();
        return role !== "admin" || elevated;
      }),
    [targetCatalog, elevated]
  );

  const createNeedsWorkspace = useMemo(
    () => executionTargetRequiresWorkspace(createTarget, targetCatalog),
    [createTarget, targetCatalog]
  );

  const refresh = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await apiFetch(`${jobsPath}?${query.toString()}`, auth);
      const j = (await res.json().catch(() => null)) as any;
      if (!res.ok || !j?.ok) {
        setErr(String(j?.detail ?? j?.error ?? res.status));
        setJobs(null);
      } else {
        setJobs(Array.isArray(j.jobs) ? (j.jobs as SchedulerJobRow[]) : []);
      }
    } catch (e) {
      setErr(String(e));
      setJobs(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.toString()]);

  useEffect(() => {
    const loadCatalog = async () => {
      try {
        const res = await apiFetch("/v1/user/scheduler-jobs/execution-targets", auth);
        const j = (await res.json().catch(() => null)) as {
          ok?: boolean;
          targets?: ExecutionTargetCatalogRow[];
        };
        if (res.ok && j?.ok && Array.isArray(j.targets)) {
          setTargetCatalog(j.targets);
        }
      } catch {
        setTargetCatalog([]);
      }
    };
    void loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // One preset directory for both scopes: the admin list read the same
  // enabled-preset set, so a single endpoint keeps the dialogs identical.
  useEffect(() => {
    const loadPresets = async () => {
      try {
        const res = await apiFetch(`/v1/user/scheduler-job-presets`, auth);
        const j = (await res.json().catch(() => null)) as any;
        if (!res.ok || !j?.ok) {
          setPresets([]);
          return;
        }
        setPresets(Array.isArray(j.presets) ? (j.presets as SchedulerJobPreset[]) : []);
      } catch {
        setPresets([]);
      }
    };
    void loadPresets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyPreset = (pid: string) => {
    const p = (presets || []).find((x) => x.id === pid);
    if (!p) return;
    const j = p.job || ({} as SchedulerJobPreset["job"]);
    if (j.execution_target) {
      setCreateTarget(normalizeExecutionTargetInput(j.execution_target, targetCatalog));
    }
    if (typeof j.interval_minutes === "number") setCreateInterval(j.interval_minutes);
    if (typeof j.enabled === "boolean") setCreateEnabled(j.enabled);
    if (typeof j.title === "string") setCreateTitle(j.title);
    if (typeof j.instructions === "string") setCreateInstructions(j.instructions);
    if (typeof j.dashboard_id === "string") setCreateDashboardId(j.dashboard_id);
    if (j.coding_workflow && typeof j.coding_workflow === "object") {
      setCreateCodingWorkflow({ ...j.coding_workflow });
    }
  };

  useEffect(() => {
    if (!createOpen || !createNeedsWorkspace) return;
    let cancelled = false;
    const load = async () => {
      setWorkspacesLoading(true);
      try {
        const res = await apiFetch("/v1/workspaces", auth);
        const j = (await res.json().catch(() => null)) as { workspaces?: WorkspaceApiRecord[] };
        if (!cancelled && res.ok) {
          setWorkspaces(Array.isArray(j?.workspaces) ? j.workspaces : []);
        }
      } catch {
        if (!cancelled) setWorkspaces([]);
      } finally {
        if (!cancelled) setWorkspacesLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [createOpen, createNeedsWorkspace, auth]);

  const toggleEnabled = async (jobId: string, next: boolean) => {
    const res = await apiFetch(`${jobsPath}/${jobId}/enabled`, auth, {
      method: "PATCH",
      body: JSON.stringify({ enabled: next }),
    });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    await refresh();
  };

  // Soft delete exists on the admin family only: a user's own job is either
  // there or hard-deleted, so the archive control has nothing to do in `/schedules`.
  const archiveJob = async (jobId: string, archived: boolean) => {
    const res = await apiFetch(`${jobsPath}/${jobId}/archived`, auth, {
      method: "PATCH",
      body: JSON.stringify({ archived }),
    });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    await refresh();
  };

  const openEdit = (j: SchedulerJobRow) => {
    setEditJob(j);
    setEditTitle(j.title ?? "");
    setEditInstructions(j.instructions ?? "");
    setEditInterval(j.interval_minutes ?? 60);
  };

  const saveEdit = async () => {
    if (!editJob) return;
    const res = await apiFetch(`${jobsPath}/${editJob.id}`, auth, {
      method: "PATCH",
      body: JSON.stringify({
        title: editTitle,
        instructions: editInstructions,
        interval_minutes: editInterval,
      }),
    });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    setEditJob(null);
    await refresh();
  };

  const hardDelete = async (jobId: string) => {
    if (!window.confirm(t("admin:schedulesPermanentDeleteConfirm"))) return;
    const res = await apiFetch(`${jobsPath}/${jobId}`, auth, { method: "DELETE" });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    await refresh();
  };

  const openRuns = async (j: SchedulerJobRow) => {
    setRunsJob(j);
    setRuns(null);
    setSelectedRun(null);
    setRunsErr(null);
    setRunsLoading(true);
    try {
      const res = await apiFetch(`${jobsPath}/${j.id}/runs?limit=25`, auth);
      const body = (await res.json().catch(() => null)) as { ok?: boolean; runs?: SchedulerJobRun[]; detail?: string };
      if (!res.ok || !body?.ok) {
        setRunsErr(String(body?.detail ?? res.status));
        setRuns([]);
      } else {
        setRuns(Array.isArray(body.runs) ? body.runs : []);
      }
    } catch (e) {
      setRunsErr(String(e));
      setRuns([]);
    } finally {
      setRunsLoading(false);
    }
  };

  const createJob = async () => {
    setErr(null);
    const wf: Record<string, string> = {};
    if (createCodingWorkflow.agent_id) {
      wf.agent_id = createCodingWorkflow.agent_id;
    }
    if (createCodingWorkflow.prompt_preamble?.trim()) {
      wf.prompt_preamble = createCodingWorkflow.prompt_preamble.trim();
    }
    const res = await apiFetch(`${jobsPath}`, auth, {
      method: "POST",
      body: JSON.stringify({
        execution_target: createTarget,
        interval_minutes: createInterval,
        enabled: createEnabled,
        title: createTitle || null,
        instructions: createInstructions,
        dashboard_id: createDashboardId || null,
        ...(createNeedsWorkspace
          ? {
              workspace_id: createWorkspaceId.trim(),
              coding_workflow: Object.keys(wf).length ? wf : {},
            }
          : { coding_workflow: {} }),
      }),
    });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    setCreateOpen(false);
    setCreatePresetId("");
    setCreateTitle("");
    setCreateInstructions("");
    setCreateDashboardId("");
    setCreateWorkspaceId("");
    setCreateCodingWorkflow({});
    await refresh();
  };

  // Built inside the component because the headers and two of the cells read
  // `t`, and the target column reads the catalog the page fetches separately.
  const jobColumns: Array<TableColumn<SchedulerJobRow>> = [
    {
      key: "enabled",
      header: t("settings:schedulesEnabledHeader"),
      width: "7rem",
      render: (j) => (
        <>
          <Badge tone={pill(j.enabled)}>
            {j.enabled ? t("settings:schedulesEnabled") : t("settings:schedulesDisabled")}
          </Badge>
          {admin && j.deleted_at ? (
            <Badge tone="neutral" className="ml-base">
              {t("admin:schedulesArchivedLabel")}
            </Badge>
          ) : null}
        </>
      ),
    },
    {
      key: "target",
      header: t("settings:schedulesTargetHeader"),
      render: (j) => labelForExecutionTarget(j.execution_target, targetCatalog),
    },
    {
      key: "title",
      header: t("settings:schedulesTitleHeader"),
      render: (j) => <span className="text-ink-primary">{j.title || "—"}</span>,
    },
    {
      key: "interval",
      header: t("settings:schedulesIntervalHeader"),
      render: (j) => t("settings:schedulesIntervalMinutes", { minutes: j.interval_minutes }),
    },
    {
      key: "dashboard",
      header: t("settings:schedulesDashboardHeader"),
      render: (j) => (
        <span className="font-mono text-ink-muted">
          {j.dashboard_id || t("settings:schedulesDashboardGlobal")}
        </span>
      ),
    },
    {
      key: "last_run",
      header: t("settings:schedulesLastRunHeader"),
      render: (j) => formatDateTimeLocal(j.last_run_at),
    },
    {
      key: "created",
      header: t("settings:schedulesCreatedHeader"),
      render: (j) => formatDateTimeLocal(j.created_at),
    },
    {
      key: "actions",
      header: t("settings:schedulesActionsHeader"),
      render: (j) => (
        <div className="flex flex-wrap items-center gap-base">
          <Button
            size="sm"
            type="button"
            className="px-base py-tight text-xs hover:bg-white/5"
            onClick={() => void toggleEnabled(j.id, !j.enabled)}
          >
            {j.enabled ? t("admin:schedulesDisable") : t("admin:schedulesEnable")}
          </Button>
          {executionTargetRequiresWorkspace(j.execution_target, targetCatalog) ? (
            <Button
              size="sm"
              type="button"
              className="px-base py-tight text-xs hover:bg-white/5"
              onClick={() => void openRuns(j)}
            >
              {t("settings:schedulesRuns")}
            </Button>
          ) : null}
          <Button
            size="sm"
            type="button"
            className="px-base py-tight text-xs hover:bg-white/5"
            onClick={() => openEdit(j)}
          >
            {t("admin:schedulesEdit")}
          </Button>
          {admin ? (
            <Button
              size="sm"
              type="button"
              className="px-base py-tight text-xs hover:bg-white/5"
              onClick={() => void archiveJob(j.id, !j.deleted_at)}
            >
              {j.deleted_at ? t("admin:schedulesUnarchive") : t("admin:schedulesArchive")}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={() => void hardDelete(j.id)}
          >
            {t("admin:schedulesDelete")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-pageWide px-broad py-page">
      <div className="flex items-start justify-between gap-wide">
        <div>
          <h1 className="text-2xl font-semibold text-ink-primary">
            {admin ? t("admin:schedulesTitle") : t("common:nav.schedules")}
          </h1>
          {admin ? (
            <p className="mt-base text-sm text-ink-muted">{t("admin:schedulesIntro")}</p>
          ) : (
            <p className="mt-base text-sm text-ink-muted">
              {t("settings:schedulesPageIntro")}{" "}
              <span className="font-mono">general</span>{" "}
              <span className="font-mono">coding</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-base">
          <Button
            type="button"
            className="px-soft py-base text-sm hover:bg-white/5"
            onClick={() => setCreateOpen(true)}
          >
            {t("admin:schedulesCreate")}
          </Button>
          <Button
            type="button"
            className="px-soft py-base text-sm hover:bg-white/5"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? t("settings:schedulesLoading") : t("settings:schedulesRefresh")}
          </Button>
        </div>
      </div>

      {admin ? (
        <div className="mt-broad rounded-sheet border border-line bg-card p-wide">
          <div className="grid gap-soft md:grid-cols-5">
            <label className="text-xs text-ink-muted">
              {t("admin:schedulesScope")}
              <Select
                className="mt-tight"
                value={scopeFilter}
                onChange={(e) => setScopeFilter(e.target.value as JobOwnerScope)}
              >
                <option value="all">{t("admin:schedulesScopeAll")}</option>
                <option value="global_only">{t("admin:schedulesScopeGlobalOnly")}</option>
                <option value="dashboard">{t("admin:schedulesScopeDashboard")}</option>
              </Select>
            </label>
            <label className="text-xs text-ink-muted md:col-span-2">
              {t("admin:schedulesDashboardId")}
              <TextInput
                className="mt-tight"
                value={dashboardId}
                onChange={(e) => setDashboardId(e.target.value)}
                placeholder={t("admin:optional")}
                disabled={scopeFilter !== "dashboard"}
              />
            </label>
            <label className="text-xs text-ink-muted">
              {t("admin:schedulesTarget")}
              <Select
                className="mt-tight"
                value={targetFilter}
                onChange={(e) => setTargetFilter(e.target.value)}
              >
                <option value="all">{t("admin:schedulesScopeAll")}</option>
                {targetCatalog.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="text-xs text-ink-muted">
              {t("admin:schedulesEnabledFilter")}
              <Select
                className="mt-tight"
                value={enabledFilter}
                onChange={(e) => setEnabledFilter(e.target.value as "all" | "true" | "false")}
              >
                <option value="all">{t("admin:schedulesScopeAll")}</option>
                <option value="true">{t("admin:schedulesEnabledFilterEnabled")}</option>
                <option value="false">{t("admin:schedulesEnabledFilterDisabled")}</option>
              </Select>
            </label>
          </div>
          {scopeFilter === "dashboard" ? (
            <label className="mt-soft flex items-center gap-base text-xs text-ink-muted">
              <Checkbox
                checked={includeGlobal}
                onChange={(e) => setIncludeGlobal(e.target.checked)}
              />
              {t("admin:schedulesIncludeGlobal")}
            </label>
          ) : null}
          <label className="mt-soft flex items-center gap-base text-xs text-ink-muted">
            <Checkbox
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            {t("admin:schedulesShowArchived")}
          </label>
        </div>
      ) : null}

      {err ? <div className="mt-wide rounded-card border border-danger/30 bg-danger-subtle p-soft text-sm text-badge-danger">{err}</div> : null}

      {/* No `rowHeight`: the tallest cell is the `h-7` action Button, so a job row is
          28 + `py-base` (8+8) = 44 px — the height the skeleton already uses for the
          `normal` density, which is why the list does not jump when the jobs land. */}
      <Table
        className="mt-broad rounded-sheet border border-line"
        columns={jobColumns}
        rows={jobs ?? []}
        rowKey={(j) => j.id}
        minWidth={admin ? "900px" : undefined}
        loading={jobs === null && !err}
        empty={
          admin ? (
            <EmptyState
              pose={jobs ? "noResults" : "waiting"}
              title={jobs ? t("admin:schedulesNone") : t("admin:schedulesNoDataYet")}
              animated={false}
            />
          ) : jobs === null ? (
            t("settings:schedulesNoData")
          ) : (
            t("settings:schedulesNoneYet")
          )
        }
      />

      {createOpen ? (
        <Modal
          open
          onClose={() => setCreateOpen(false)}
          title={t("admin:createScheduleTitle")}
          size="dialogWide"
          footer={
            <>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={() => setCreateOpen(false)}
              >
                {t("admin:cancel")}
              </Button>
              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={() => void createJob()}
                disabled={
                  !createInstructions.trim() ||
                  (createNeedsWorkspace && !createWorkspaceId.trim())
                }
              >
                {t("admin:create")}
              </Button>
            </>
          }
        >
          <p className="text-meta text-ink-muted">
            {admin ? t("admin:createScheduleHelp") : t("admin:schedulesCreateHelpUser")}
          </p>

          <div className="mt-soft grid gap-soft md:grid-cols-2">
              <label className="text-xs text-ink-muted md:col-span-2">
                {t("admin:schedulesPresetOptional")}
                <Select
                  className="mt-tight"
                  value={createPresetId}
                  onChange={(e) => {
                    const pid = e.target.value;
                    setCreatePresetId(pid);
                    if (pid) applyPreset(pid);
                  }}
                >
                  <option value="">—</option>
                  {(presets || []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </Select>
                {createPresetId && (presets || []).find((p) => p.id === createPresetId)?.description ? (
                  <div className="mt-tight text-meta text-ink-muted">
                    {(presets || []).find((p) => p.id === createPresetId)?.description}
                  </div>
                ) : null}
              </label>

              <label className="text-xs text-ink-muted">
                {t("settings:schedulesTargetHeader")}
                <Select
                  className="mt-tight"
                  value={createTarget}
                  onChange={(e) =>
                    setCreateTarget(normalizeExecutionTargetInput(e.target.value, targetCatalog))
                  }
                >
                  {createTargetOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </label>
              {createNeedsWorkspace ? (
                <label className="text-xs text-ink-muted md:col-span-2">
                  {t("settings:schedulesWorkspaceRequired")}
                  <Select
                    className="mt-tight"
                    value={createWorkspaceId}
                    onChange={(e) => setCreateWorkspaceId(e.target.value)}
                    disabled={workspacesLoading}
                  >
                    <option value="">
                      {workspacesLoading
                        ? t("settings:schedulesLoadingWorkspaces")
                        : workspaces.length === 0
                          ? t("settings:schedulesNoWorkspacesHint")
                          : t("settings:schedulesSelectWorkspace")}
                    </option>
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </Select>
                  {createWorkspaceId ? (
                    <div className="mt-tight break-all font-mono text-meta text-ink-muted">
                      {createWorkspaceId}
                    </div>
                  ) : null}
                  {createCodingWorkflow.agent_id ? (
                    <div className="mt-tight font-mono text-meta text-ink-muted">
                      Agent: {createCodingWorkflow.agent_id}
                    </div>
                  ) : null}
                </label>
              ) : null}
              <label className="text-xs text-ink-muted">
                {t("settings:schedulesIntervalHeader")} (minutes)
                <TextInput
                  type="number"
                  className="mt-tight"
                  value={createInterval}
                  onChange={(e) => setCreateInterval(Number(e.target.value))}
                  min={5}
                  max={10080}
                />
              </label>
              <label className="text-xs text-ink-muted md:col-span-2">
                {t("settings:schedulesTitleHeader")}
                <TextInput
                  className="mt-tight"
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  placeholder={t("admin:optional")}
                />
              </label>
              <label className="text-xs text-ink-muted md:col-span-2">
                {t("admin:schedulesDashboardIdOptional")}
                <TextInput
                  className="mt-tight"
                  value={createDashboardId}
                  onChange={(e) => setCreateDashboardId(e.target.value)}
                  placeholder={t("admin:optional")}
                />
              </label>
              <label className="text-xs text-ink-muted md:col-span-2">
                <span>{t("admin:instructionsPlaceholder")}</span>
                <TextArea
                  className="mt-tight min-h-[120px] resize-y"
                  value={createInstructions}
                  onChange={(e) => setCreateInstructions(e.target.value)}
                  placeholder={t("admin:instructionsPlaceholder")}
                />
              </label>
              <label className="flex items-center gap-base text-xs text-ink-muted">
                <Checkbox
                  checked={createEnabled}
                  onChange={(e) => setCreateEnabled(e.target.checked)}
                />
                {t("settings:schedulesEnabledHeader")}
              </label>
            </div>
        </Modal>
      ) : null}

      {editJob ? (
        <Modal
          open
          onClose={() => setEditJob(null)}
          title={t("settings:schedulesEditTitle")}
          size="dialogWide"
          footer={
            <>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={() => setEditJob(null)}
              >
                {t("admin:cancel")}
              </Button>
              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={() => void saveEdit()}
                disabled={!editInstructions.trim()}
              >
                {t("admin:save")}
              </Button>
            </>
          }
        >
          <p className="font-mono text-meta text-ink-muted">id: {editJob.id}</p>
          <div className="mt-soft grid gap-soft">
              <label className="text-xs text-ink-muted">
                {t("settings:schedulesTitleHeader")}
                <TextInput
                  className="mt-tight"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </label>
              <label className="text-xs text-ink-muted">
                {t("settings:schedulesIntervalHeader")} (minutes)
                <TextInput
                  type="number"
                  className="mt-tight"
                  value={editInterval}
                  onChange={(e) => setEditInterval(Number(e.target.value))}
                  min={5}
                  max={10080}
                />
              </label>
              <label className="text-xs text-ink-muted">
                <span>{t("admin:instructionsPlaceholder")}</span>
                <TextArea
                  className="mt-tight min-h-[140px] resize-y"
                  value={editInstructions}
                  onChange={(e) => setEditInstructions(e.target.value)}
                />
              </label>
            </div>
        </Modal>
      ) : null}

      {runsJob ? (
        <Modal
          open
          onClose={() => {
            setRunsJob(null);
            setSelectedRun(null);
          }}
          title={t("settings:schedulesRunHistoryTitle")}
          size="dialogFull"
        >
          <p className="text-body text-ink-muted">{runsJob.title || "—"}</p>
          <p className="font-mono text-meta text-ink-muted">{runsJob.id}</p>

          {runsErr ? (
            <p className="mt-base rounded-card border border-danger bg-danger-subtle p-base text-sm text-badge-danger">
              {runsErr}
            </p>
          ) : null}

          {/*
            The panel is `max-h-full` inside a centred overlay, so its height
            follows its content: while the runs are in flight the dialog is a
            few lines tall and every later state — the list landing, a run
            being selected — grows it and pulls the whole dialog back to the
            middle. `md:h-[min(58vh,34rem)]` gives the two panes a frame that
            the request cannot change, and turns their `overflow-auto` into a
            real scroller instead of a grower. The row placeholder below covers
            the stacked layout, where no frame is set.
          */}
          <div className="mt-soft grid min-h-0 gap-soft md:h-[min(58vh,34rem)] md:grid-cols-2">
              <div className="min-h-0 overflow-auto rounded-card border border-line">
                <table className="min-w-full text-left text-xs">
                  <thead className="sticky top-0 bg-raised text-ink-muted">
                    <tr>
                      <th className="px-base py-base">{t("settings:schedulesRunColStatus")}</th>
                      <th className="px-base py-base">{t("settings:schedulesRunColStarted")}</th>
                      <th className="px-base py-base">{t("settings:schedulesRunColTools")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {runsLoading ? (
                      // 36 px is one real row: `py-base` (8+8) around the tallest
                      // cell content, which is the status `Badge` (py-hair 4 + the
                      // 16 px `text-label` line). Eight of them is what the pane
                      // shows at the frame height — the request asks for 25, and
                      // reserving all 25 would leave a metre of grey bars on a job
                      // that ran twice.
                      <tr>
                        <td className="p-0" colSpan={3}>
                          <span className="sr-only">{t("settings:schedulesRunsLoading")}</span>
                          <SkeletonRows rows={8} rowHeight={36} columns={["22%", "52%", "12%"]} />
                        </td>
                      </tr>
                    ) : !runs?.length ? (
                      <tr>
                        <td className="px-base py-soft text-ink-muted" colSpan={3}>
                          {t("settings:schedulesNoRunsRecorded")}
                        </td>
                      </tr>
                    ) : (
                      runs.map((r) => (
                        <tr
                          key={r.id}
                          className={`cursor-pointer hover:bg-white/5 ${selectedRun?.id === r.id ? "bg-white/10" : ""}`}
                          onClick={() => setSelectedRun(r)}
                        >
                          <td className="px-base py-base">
                            <Badge tone={runStatusPill(r.status)}>{r.status}</Badge>
                          </td>
                          <td className="px-base py-base text-meta text-ink-muted">
                            {formatDateTimeLocal(r.started_at)}
                          </td>
                          <td className="px-base py-base text-ink-muted">
                            {r.summary_json?.tool_count ?? r.summary_json?.tools?.length ?? 0}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="min-h-0 overflow-auto rounded-card border border-line p-soft text-xs">
                {!selectedRun ? (
                <p className="text-ink-muted">{t("settings:schedulesRunSelectHint")}</p>
                ) : (
                  <div className="space-y-soft">
                    <div>
                      <Badge tone={runStatusPill(selectedRun.status)}>
                        {selectedRun.status}
                      </Badge>
                      {selectedRun.summary_json?.outcome ? (
                        <span className="ml-base text-ink-muted">({selectedRun.summary_json.outcome})</span>
                      ) : null}
                      {selectedRun.summary_json?.duration_ms != null ? (
                        <span className="ml-base text-ink-muted">
                          {Math.round(selectedRun.summary_json.duration_ms / 1000)}s
                        </span>
                      ) : null}
                    </div>
                    {selectedRun.error ? (
                      <div className="rounded-tile border border-danger/30 bg-danger-subtle p-base text-badge-danger">{selectedRun.error}</div>
                    ) : null}
                    {selectedRun.summary_json?.git ? (
                      <div>
                        <div className="font-medium text-ink-primary">{t("settings:schedulesRunGit")}</div>
                        <div className="text-ink-muted">
                          branch: {selectedRun.summary_json.git.branch || "—"} · changes:{" "}
                          {selectedRun.summary_json.git.has_changes ? "yes" : "no"}
                        </div>
                      </div>
                    ) : null}
                    {(selectedRun.summary_json?.files_changed?.length ?? 0) > 0 ? (
                      <div>
                        <div className="font-medium text-ink-primary">{t("settings:schedulesRunChangedFiles")}</div>
                        <ul className="mt-tight space-y-hair font-mono text-meta text-ink-muted">
                          {selectedRun.summary_json.files_changed!.map((f) => (
                            <li key={f.path}>
                              {f.path} {f.stat ? `| ${f.stat}` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {(selectedRun.summary_json?.tools?.length ?? 0) > 0 ? (
                      <div>
                        <div className="font-medium text-ink-primary">{t("settings:schedulesRunTools")}</div>
                        <ul className="mt-tight max-h-48 space-y-tight overflow-auto font-mono text-meta">
                          {selectedRun.summary_json.tools!.map((t, i) => (
                            <li
                              key={`${t.round}-${t.name}-${i}`}
                              className={t.ok ? "text-badge-success" : "text-badge-danger"}
                            >
                              r{t.round} {t.name}
                              {t.args?.path ? ` path=${String(t.args.path)}` : ""}
                              {t.error ? ` — ${t.error}` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {selectedRun.summary_json?.final_reply_excerpt ? (
                      <div>
                        <div className="font-medium text-ink-primary">{t("settings:schedulesRunReplyExcerpt")}</div>
                        <pre className="mt-tight whitespace-pre-wrap rounded-tile bg-black/30 p-base text-meta text-ink-muted">
                          {selectedRun.summary_json.final_reply_excerpt}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </div>
        </Modal>
      ) : null}
    </div>
  );
}