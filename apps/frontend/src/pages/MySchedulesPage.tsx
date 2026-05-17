import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, type WorkspaceApiRecord } from "../lib/api";

type SchedulerJobRow = {
  id: string;
  dashboard_id: string | null;
  execution_target: string;
  title: string | null;
  interval_minutes: number;
  enabled: boolean;
  last_run_at: string | null;
  created_at: string;
  instructions?: string;
};

type CodingWorkflowPreset = {
  agent_id?: "coding" | "coding_plan";
  prompt_preamble?: string;
};

type SchedulerJobPreset = {
  id: string;
  label: string;
  description?: string;
  job: {
    execution_target?: "coding_agent" | "server_periodic";
    interval_minutes?: number;
    enabled?: boolean;
    title?: string | null;
    instructions?: string;
    dashboard_id?: string | null;
    coding_workflow?: CodingWorkflowPreset;
  };
};

function pill(enabled: boolean) {
  return enabled
    ? "bg-emerald-600/25 text-emerald-200 border-emerald-500/40"
    : "bg-white/10 text-surface-muted border-surface-border";
}

export function MySchedulesPage() {
  const auth = useAuth();
  const [jobs, setJobs] = useState<SchedulerJobRow[] | null>(null);
  const [presets, setPresets] = useState<SchedulerJobPreset[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createPresetId, setCreatePresetId] = useState<string>("");
  const [createTarget, setCreateTarget] = useState<"server_periodic" | "coding_agent">("server_periodic");
  const [createWorkspaceId, setCreateWorkspaceId] = useState("");
  const [createInterval, setCreateInterval] = useState(1440);
  const [createEnabled, setCreateEnabled] = useState(false);
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

  const query = useMemo(() => {
    const q = new URLSearchParams();
    q.set("limit", "200");
    return q;
  }, []);

  const refresh = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await apiFetch(`/v1/user/scheduler-jobs?${query.toString()}`, auth);
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
  }, []);

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
    if (j.execution_target) setCreateTarget(j.execution_target);
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
    if (!createOpen || createTarget !== "coding_agent") return;
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
  }, [createOpen, createTarget, auth]);

  const toggleEnabled = async (jobId: string, next: boolean) => {
    const res = await apiFetch(`/v1/user/scheduler-jobs/${jobId}/enabled`, auth, {
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

  const openEdit = (j: SchedulerJobRow) => {
    setEditJob(j);
    setEditTitle(j.title ?? "");
    setEditInstructions(j.instructions ?? "");
    setEditInterval(j.interval_minutes ?? 60);
  };

  const saveEdit = async () => {
    if (!editJob) return;
    const res = await apiFetch(`/v1/user/scheduler-jobs/${editJob.id}`, auth, {
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
    // eslint-disable-next-line no-alert
    if (!window.confirm("Delete this schedule permanently? This cannot be undone.")) return;
    const res = await apiFetch(`/v1/user/scheduler-jobs/${jobId}`, auth, { method: "DELETE" });
    const j = (await res.json().catch(() => null)) as any;
    if (!res.ok || !j?.ok) {
      setErr(String(j?.detail ?? j?.error ?? res.status));
      return;
    }
    await refresh();
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
    const res = await apiFetch(`/v1/user/scheduler-jobs`, auth, {
      method: "POST",
      body: JSON.stringify({
        execution_target: createTarget,
        interval_minutes: createInterval,
        enabled: createEnabled,
        title: createTitle || null,
        instructions: createInstructions,
        dashboard_id: createDashboardId || null,
        ...(createTarget === "coding_agent"
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

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">My schedules</h1>
          <p className="mt-2 text-sm text-surface-muted">
            Your saved schedules (recurring jobs). RSS schedules run as <span className="font-mono">server_periodic</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-md border border-surface-border px-3 py-2 text-sm text-neutral-100 hover:bg-white/5"
            onClick={() => setCreateOpen(true)}
          >
            Create
          </button>
          <button
            type="button"
            className="rounded-md border border-surface-border px-3 py-2 text-sm text-neutral-100 hover:bg-white/5 disabled:opacity-60"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {err ? <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">{err}</div> : null}

      <div className="mt-6 overflow-x-auto rounded-xl border border-surface-border">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-surface-muted">
            <tr>
              <th className="px-3 py-3">Enabled</th>
              <th className="px-3 py-3">Target</th>
              <th className="px-3 py-3">Title</th>
              <th className="px-3 py-3">Interval</th>
              <th className="px-3 py-3">Dashboard</th>
              <th className="px-3 py-3">Last run</th>
              <th className="px-3 py-3">Created</th>
              <th className="px-3 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {jobs === null ? (
              <tr>
                <td className="px-3 py-4 text-surface-muted" colSpan={8}>
                  {loading ? "Loading…" : "No data."}
                </td>
              </tr>
            ) : jobs.length === 0 ? (
              <tr>
                <td className="px-3 py-4 text-surface-muted" colSpan={8}>
                  No schedules yet.
                </td>
              </tr>
            ) : (
              jobs.map((j) => (
                <tr key={j.id} className="hover:bg-white/2">
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${pill(j.enabled)}`}>
                      {j.enabled ? "enabled" : "disabled"}
                    </span>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-neutral-200">{j.execution_target}</td>
                  <td className="px-3 py-3 text-neutral-100">{j.title || "—"}</td>
                  <td className="px-3 py-3 text-neutral-100">{j.interval_minutes} min</td>
                  <td className="px-3 py-3 font-mono text-xs text-surface-muted">{j.dashboard_id || "global"}</td>
                  <td className="px-3 py-3 font-mono text-xs text-surface-muted">{j.last_run_at || "—"}</td>
                  <td className="px-3 py-3 font-mono text-xs text-surface-muted">{j.created_at}</td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="rounded-md border border-surface-border px-2 py-1 text-xs text-neutral-100 hover:bg-white/5"
                        onClick={() => void toggleEnabled(j.id, !j.enabled)}
                      >
                        {j.enabled ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-surface-border px-2 py-1 text-xs text-neutral-100 hover:bg-white/5"
                        onClick={() => openEdit(j)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs text-red-100 hover:bg-red-500/20"
                        onClick={() => void hardDelete(j.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-2xl rounded-xl border border-surface-border bg-surface-raised p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-white">Create schedule</div>
                <div className="text-xs text-surface-muted">Creates a new scheduler job for your user.</div>
              </div>
              <button
                type="button"
                className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-neutral-100 hover:bg-white/5"
                onClick={() => setCreateOpen(false)}
              >
                Close
              </button>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-xs text-surface-muted md:col-span-2">
                Preset (optional)
                <select
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
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
                </select>
                {createPresetId && (presets || []).find((p) => p.id === createPresetId)?.description ? (
                  <div className="mt-1 text-[11px] text-surface-muted">
                    {(presets || []).find((p) => p.id === createPresetId)?.description}
                  </div>
                ) : null}
              </label>

              <label className="text-xs text-surface-muted">
                Target
                <select
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={createTarget}
                  onChange={(e) => setCreateTarget(e.target.value as any)}
                >
                  <option value="server_periodic">server_periodic</option>
                  {auth.user?.role === "admin" ? (
                    <option value="coding_agent">coding_agent</option>
                  ) : null}
                </select>
              </label>
              {createTarget === "coding_agent" ? (
                <label className="text-xs text-surface-muted md:col-span-2">
                  Project workspace (required)
                  <select
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100 disabled:opacity-60"
                    value={createWorkspaceId}
                    onChange={(e) => setCreateWorkspaceId(e.target.value)}
                    disabled={workspacesLoading}
                  >
                    <option value="">
                      {workspacesLoading
                        ? "Loading workspaces…"
                        : workspaces.length === 0
                          ? "No workspaces — create one in Coding Agent"
                          : "— select workspace —"}
                    </option>
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                  {createWorkspaceId ? (
                    <div className="mt-1 break-all font-mono text-[11px] text-surface-muted">
                      {createWorkspaceId}
                    </div>
                  ) : null}
                  {createCodingWorkflow.agent_id ? (
                    <div className="mt-1 font-mono text-[11px] text-surface-muted">
                      Agent: {createCodingWorkflow.agent_id}
                    </div>
                  ) : null}
                </label>
              ) : null}
              <label className="text-xs text-surface-muted">
                Interval (minutes)
                <input
                  type="number"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={createInterval}
                  onChange={(e) => setCreateInterval(Number(e.target.value))}
                  min={5}
                  max={10080}
                />
              </label>
              <label className="text-xs text-surface-muted md:col-span-2">
                Title
                <input
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  placeholder="optional"
                />
              </label>
              <label className="text-xs text-surface-muted md:col-span-2">
                Dashboard id (optional UUID; blank = global)
                <input
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={createDashboardId}
                  onChange={(e) => setCreateDashboardId(e.target.value)}
                  placeholder="optional"
                />
              </label>
              <label className="text-xs text-surface-muted md:col-span-2">
                <span>Instructions</span>
                <textarea
                  className="mt-1 min-h-[120px] w-full resize-y rounded-md border border-surface-border bg-black/30 px-2 py-2 text-sm text-neutral-100"
                  value={createInstructions}
                  onChange={(e) => setCreateInstructions(e.target.value)}
                  placeholder="What should the agent do?"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-surface-muted">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-surface-border"
                  checked={createEnabled}
                  onChange={(e) => setCreateEnabled(e.target.checked)}
                />
                Enabled
              </label>
            </div>

            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-surface-border px-3 py-2 text-sm text-neutral-100 hover:bg-white/5"
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-violet-600/80 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
                onClick={() => void createJob()}
                disabled={
                  !createInstructions.trim() ||
                  (createTarget === "coding_agent" && !createWorkspaceId.trim())
                }
              >
                Create
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {editJob ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-2xl rounded-xl border border-surface-border bg-surface-raised p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-white">Edit schedule</div>
                <div className="text-xs text-surface-muted font-mono">id: {editJob.id}</div>
              </div>
              <button
                type="button"
                className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-neutral-100 hover:bg-white/5"
                onClick={() => setEditJob(null)}
              >
                Close
              </button>
            </div>
            <div className="grid gap-3">
              <label className="text-xs text-surface-muted">
                Title
                <input
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </label>
              <label className="text-xs text-surface-muted">
                Interval (minutes)
                <input
                  type="number"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/30 px-2 py-1 text-sm text-neutral-100"
                  value={editInterval}
                  onChange={(e) => setEditInterval(Number(e.target.value))}
                  min={5}
                  max={10080}
                />
              </label>
              <label className="text-xs text-surface-muted">
                Instructions
                <textarea
                  className="mt-1 min-h-[140px] w-full resize-y rounded-md border border-surface-border bg-black/30 px-2 py-2 text-sm text-neutral-100"
                  value={editInstructions}
                  onChange={(e) => setEditInstructions(e.target.value)}
                />
              </label>
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-surface-border px-3 py-2 text-sm text-neutral-100 hover:bg-white/5"
                onClick={() => setEditJob(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-violet-600/80 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
                onClick={() => void saveEdit()}
                disabled={!editInstructions.trim()}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

