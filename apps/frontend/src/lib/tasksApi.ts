import { apiFetch } from "./api";
import type { AuthContextValue } from "../auth/AuthContext";

export type Task = {
  id: string;
  scope: "global" | "workspace";
  workspace_id?: string | null;
  parent_task_id?: string | null;
  goal: string;
  status: string;
  priority: string;
  assigned_agent_id?: string | null;
  artifact_refs?: string[];
  task_type?: string;
  updated_at?: string;
};

export type TaskDetail = {
  task: Task;
  subtasks: Task[];
  artifacts: { id: string; kind: string; summary: string }[];
};

export async function fetchTasks(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  params?: { scope?: string; workspace_id?: string; root_only?: boolean }
): Promise<Task[]> {
  const q = new URLSearchParams();
  if (params?.scope) q.set("scope", params.scope);
  if (params?.workspace_id) q.set("workspace_id", params.workspace_id);
  if (params?.root_only) q.set("root_only", "true");
  const path = `/v1/tasks${q.toString() ? `?${q}` : ""}`;
  const res = await apiFetch(path, auth);
  const data = (await res.json()) as { tasks?: Task[] };
  return data.tasks ?? [];
}

export async function fetchTask(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  taskId: string
): Promise<TaskDetail | null> {
  const res = await apiFetch(`/v1/tasks/${encodeURIComponent(taskId)}`, auth);
  if (!res.ok) return null;
  return (await res.json()) as TaskDetail;
}

export async function createTask(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  body: {
    scope: "global" | "workspace";
    goal: string;
    workspace_id?: string;
    parent_task_id?: string;
    conversation_id?: string;
  }
): Promise<Task> {
  const res = await apiFetch("/v1/tasks", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as { task: Task };
  return data.task;
}

export async function patchTask(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  taskId: string,
  body: { status?: string; goal?: string; priority?: string }
): Promise<Task> {
  const res = await apiFetch(`/v1/tasks/${encodeURIComponent(taskId)}`, auth, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as { task: Task };
  return data.task;
}

export async function setConversationActiveTask(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  conversationId: string,
  activeTaskId: string | null
): Promise<void> {
  await apiFetch(
    `/v1/user/conversations/${encodeURIComponent(conversationId)}/active-task`,
    auth,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_task_id: activeTaskId }),
    }
  );
}
