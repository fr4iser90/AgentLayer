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
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<SessionRuntimePayload | null> {
  const r = await apiFetch("/v1/session/runtime", auth);
  if (!r.ok) return null;
  return r.json() as Promise<SessionRuntimePayload>;
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
