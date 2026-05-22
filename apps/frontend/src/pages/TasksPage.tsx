import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../lib/api";
import {
  createTask,
  fetchTasks,
  patchTask,
  setConversationActiveTask,
  type Task,
} from "../lib/tasksApi";

type WorkspaceRow = { id: string; name: string };

async function fetchWorkspaces(
  auth: ReturnType<typeof useAuth>
): Promise<WorkspaceRow[]> {
  const r = await apiFetch("/v1/workspaces", auth);
  const data = (await r.json()) as { workspaces?: { id: string; name: string }[] };
  return (data.workspaces ?? []).map((w) => ({ id: w.id, name: w.name }));
}

function TaskList({
  tasks,
  activeTaskId,
  onBind,
  onDone,
}: {
  tasks: Task[];
  activeTaskId: string | null;
  onBind: (id: string) => void;
  onDone: (id: string) => void;
}) {
  if (tasks.length === 0) {
    return <p className="text-sm text-surface-muted">No tasks yet.</p>;
  }
  return (
    <ul className="space-y-2">
      {tasks.map((t) => (
        <li
          key={t.id}
          className={[
            "rounded-lg border px-3 py-2.5",
            activeTaskId === t.id
              ? "border-indigo-500/50 bg-indigo-950/30"
              : "border-surface-border bg-surface-raised/50",
          ].join(" ")}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-surface-muted">
                {t.status}
              </span>
              <p className="mt-0.5 text-sm text-neutral-200">{t.goal}</p>
            </div>
            <div className="flex shrink-0 flex-col gap-1">
              <button
                type="button"
                className="rounded border border-white/10 px-2 py-1 text-[11px] text-neutral-300 hover:bg-white/5"
                onClick={() => onBind(t.id)}
              >
                {activeTaskId === t.id ? "Bound to chat" : "Bind to chat"}
              </button>
              {t.status !== "done" ? (
                <button
                  type="button"
                  className="rounded border border-emerald-500/30 px-2 py-1 text-[11px] text-emerald-300/90 hover:bg-emerald-950/40"
                  onClick={() => onDone(t.id)}
                >
                  Mark done
                </button>
              ) : null}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function TasksPage() {
  const auth = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const conversationId = searchParams.get("conversation")?.trim() || null;
  const workspaceParam = searchParams.get("workspace")?.trim() || null;

  const [workspaces, setWorkspaces] = useState<WorkspaceRow[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    workspaceParam
  );
  const [globalTasks, setGlobalTasks] = useState<Task[]>([]);
  const [workspaceTasks, setWorkspaceTasks] = useState<Task[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [globalGoal, setGlobalGoal] = useState("");
  const [projectGoal, setProjectGoal] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId]
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [global, ws] = await Promise.all([
        fetchTasks(auth, { scope: "global", root_only: true }),
        selectedWorkspaceId
          ? fetchTasks(auth, {
              scope: "workspace",
              workspace_id: selectedWorkspaceId,
              root_only: true,
            })
          : Promise.resolve([] as Task[]),
      ]);
      setGlobalTasks(global);
      setWorkspaceTasks(ws);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [auth, selectedWorkspaceId]);

  useEffect(() => {
    void fetchWorkspaces(auth).then(setWorkspaces).catch(() => setWorkspaces([]));
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (workspaceParam) setSelectedWorkspaceId(workspaceParam);
  }, [workspaceParam]);

  const bindToChat = async (taskId: string) => {
    setActiveTaskId(taskId);
    if (conversationId) {
      try {
        await setConversationActiveTask(auth, conversationId, taskId);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to bind task to chat");
      }
    }
  };

  const clearBind = async () => {
    setActiveTaskId(null);
    if (conversationId) {
      try {
        await setConversationActiveTask(auth, conversationId, null);
      } catch {
        /* ignore */
      }
    }
  };

  const onWorkspaceChange = (id: string) => {
    const next = id || null;
    setSelectedWorkspaceId(next);
    const p = new URLSearchParams(searchParams);
    if (next) p.set("workspace", next);
    else p.delete("workspace");
    setSearchParams(p, { replace: true });
  };

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-white">Tasks</h1>
            <p className="mt-1 text-sm text-surface-muted">
              Backlog for orchestration (global) and project work (per workspace). Chat only
              uses a bound task — manage everything here.
            </p>
          </div>
          <Link
            to={conversationId ? `/chat?c=${encodeURIComponent(conversationId)}` : "/chat"}
            className="rounded-lg border border-white/10 px-3 py-2 text-sm text-sky-400/90 hover:bg-white/5"
          >
            ← Back to chat
          </Link>
        </div>

        {conversationId ? (
          <div className="mt-4 rounded-lg border border-indigo-500/35 bg-indigo-950/25 px-4 py-3 text-sm text-indigo-100/90">
            Binding tasks to chat{" "}
            <span className="font-mono text-xs text-indigo-200/80">
              {conversationId.slice(0, 8)}…
            </span>
            . Use &quot;Bind to chat&quot; on a task below.
            {activeTaskId ? (
              <button
                type="button"
                className="ml-3 text-xs text-surface-muted underline hover:text-neutral-300"
                onClick={() => void clearBind()}
              >
                Clear binding
              </button>
            ) : null}
          </div>
        ) : null}

        {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}

        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-surface-muted">
            Global tasks
          </h2>
          <p className="mt-1 text-xs text-surface-muted">
            Cross-project goals (no workspace). Not mixed with project tasks.
          </p>
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={globalGoal}
              onChange={(e) => setGlobalGoal(e.target.value)}
              placeholder="New global goal…"
              className="min-w-0 flex-1 rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-neutral-200"
            />
            <button
              type="button"
              className="shrink-0 rounded-lg border border-indigo-500/40 bg-indigo-500/15 px-4 py-2 text-sm text-indigo-200"
              onClick={() => {
                const g = globalGoal.trim();
                if (!g) return;
                void createTask(auth, { scope: "global", goal: g, conversation_id: conversationId ?? undefined })
                  .then(() => {
                    setGlobalGoal("");
                    return reload();
                  })
                  .catch(() => undefined);
              }}
            >
              Add
            </button>
          </div>
          <div className="mt-4">
            {loading ? (
              <p className="text-sm text-surface-muted">Loading…</p>
            ) : (
              <TaskList
                tasks={globalTasks}
                activeTaskId={activeTaskId}
                onBind={(id) => void bindToChat(id)}
                onDone={(id) =>
                  void patchTask(auth, id, { status: "done" }).then(() => reload())
                }
              />
            )}
          </div>
        </section>

        <section className="mt-10 border-t border-surface-border pt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-surface-muted">
            Project tasks
          </h2>
          <p className="mt-1 text-xs text-surface-muted">
            Scoped to one workspace / repo.
          </p>
          <label className="mt-3 block text-xs text-surface-muted">
            Workspace
            <select
              className="mt-1 block w-full max-w-md rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-neutral-200"
              value={selectedWorkspaceId ?? ""}
              onChange={(e) => onWorkspaceChange(e.target.value)}
            >
              <option value="">Select a project…</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          {selectedWorkspaceId ? (
            <>
              <div className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={projectGoal}
                  onChange={(e) => setProjectGoal(e.target.value)}
                  placeholder={
                    selectedWorkspace
                      ? `New task for ${selectedWorkspace.name}…`
                      : "New project task…"
                  }
                  className="min-w-0 flex-1 rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-neutral-200"
                />
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm text-sky-200"
                  onClick={() => {
                    const g = projectGoal.trim();
                    if (!g || !selectedWorkspaceId) return;
                    void createTask(auth, {
                      scope: "workspace",
                      goal: g,
                      workspace_id: selectedWorkspaceId,
                      conversation_id: conversationId ?? undefined,
                    })
                      .then(() => {
                        setProjectGoal("");
                        return reload();
                      })
                      .catch(() => undefined);
                  }}
                >
                  Add
                </button>
              </div>
              <div className="mt-4">
                {loading ? (
                  <p className="text-sm text-surface-muted">Loading…</p>
                ) : (
                  <TaskList
                    tasks={workspaceTasks}
                    activeTaskId={activeTaskId}
                    onBind={(id) => void bindToChat(id)}
                    onDone={(id) =>
                      void patchTask(auth, id, { status: "done" }).then(() => reload())
                    }
                  />
                )}
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-surface-muted">
              Choose a workspace to see and create project tasks.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
