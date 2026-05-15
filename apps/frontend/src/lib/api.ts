import type { AuthContextValue } from "../auth/AuthContext";

export type AgentDefinition = {
  id: string;
  name: string;
  icon: string;
  description: string;
  system_prompt: string;
  tool_domain: string | null;
  tool_names: string[];
  requires_workspace: boolean;
  execution_context: string;
  min_role: string;
  model_profile: string | null;
};

export async function fetchAgents(auth: Pick<AuthContextValue, "accessToken" | "refresh">): Promise<AgentDefinition[]> {
  const r = await apiFetch("/v1/agents", auth);
  if (!r.ok) return [];
  return r.json() as Promise<AgentDefinition[]>;
}

export type McpServerRuntime = {
  id: string;
  command: string;
  args: string[];
  cwd: string | null;
  connected: boolean;
  tool_count: number;
  error: string | null;
};

export type SessionRuntimePayload = {
  mcp: {
    enabled: boolean;
    import_ok: boolean;
    agent_ids: string[];
    servers: McpServerRuntime[];
    config_error?: string;
    error?: string;
    /** ``workspace`` when status used per-workspace MCP JSON from the DB row. */
    scope?: "global" | "workspace";
  };
};

export type TokenUsageTotals = {
  prompt: number;
  completion: number;
  total: number;
  rounds: number;
};

export const emptyTokenUsage = (): TokenUsageTotals => ({
  prompt: 0,
  completion: 0,
  total: 0,
  rounds: 0,
});

/** Merge OpenAI-style ``usage`` objects from ``agent.llm_round`` / ``chat.completion`` events. */
export function addUsageTotals(prev: TokenUsageTotals, usage: unknown): TokenUsageTotals {
  if (!usage || typeof usage !== "object") return prev;
  const u = usage as Record<string, unknown>;
  const p = Number(u.prompt_tokens ?? u.prompt ?? 0) || 0;
  const c = Number(u.completion_tokens ?? u.completion ?? 0) || 0;
  const stated = Number(u.total_tokens ?? u.total ?? 0) || 0;
  const lineTotal = stated > 0 ? stated : p + c;
  const bump = p > 0 || c > 0 || stated > 0;
  return {
    prompt: prev.prompt + p,
    completion: prev.completion + c,
    total: prev.total + lineTotal,
    rounds: prev.rounds + (bump ? 1 : 0),
  };
}

export async function fetchSessionRuntime(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  workspaceId?: string | null
): Promise<SessionRuntimePayload | null> {
  const wid = typeof workspaceId === "string" ? workspaceId.trim() : "";
  const qs = wid ? `?workspace_id=${encodeURIComponent(wid)}` : "";
  const r = await apiFetch(`/v1/session/runtime${qs}`, auth);
  if (!r.ok) return null;
  return r.json() as Promise<SessionRuntimePayload>;
}

export type WorkspaceApiRecord = {
  id: string;
  owner_user_id: string;
  name: string;
  path: string;
  source: string;
  git_url: string | null;
  git_branch: string;
  access_role: "owner" | "editor" | "viewer";
  created_at: string | null;
  updated_at: string | null;
  verify_command?: string | null;
  verify_required?: boolean;
  mcp_stdio_servers?: Array<Record<string, unknown>> | null;
};

export async function patchWorkspace(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  workspaceId: string,
  body: Record<string, unknown>
): Promise<{ ok: true; workspace: WorkspaceApiRecord } | { ok: false; error: string }> {
  const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(workspaceId)}`, auth, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const j = (await r.json().catch(() => ({}))) as { detail?: unknown };
    const d = j.detail;
    const msg =
      typeof d === "string" ? d : Array.isArray(d) && d[0] && typeof (d[0] as { msg?: string }).msg === "string"
        ? (d[0] as { msg: string }).msg
        : `HTTP ${r.status}`;
    return { ok: false, error: msg };
  }
  const j = (await r.json()) as { workspace: WorkspaceApiRecord };
  return { ok: true, workspace: j.workspace };
}

/**
 * Authenticated fetch with one retry after POST /auth/refresh on 401.
 */
export async function apiFetch(
  path: string,
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  init?: RequestInit
): Promise<Response> {
  const url = path.startsWith("/") ? path : `/${path}`;
  const run = async (token: string | null) => {
    const headers = new Headers(init?.headers);
    if (
      init?.body != null &&
      !(init.body instanceof FormData) &&
      !headers.has("Content-Type")
    ) {
      headers.set("Content-Type", "application/json");
    }
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    return fetch(url, { ...init, credentials: "include", headers });
  };

  let token = auth.accessToken;
  let res = await run(token);
  if (res.status === 401) {
    const next = await auth.refresh();
    if (next) {
      res = await run(next);
    }
  }
  return res;
}
