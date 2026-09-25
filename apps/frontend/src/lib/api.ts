import i18n from "i18next";
import type { AuthContextValue } from "../auth/AuthContext";
import { accessTokenNeedsRefresh } from "../auth/tokenRefresh";
import { toast } from "../ui/toastBus";
import { detectUserTimezone, USER_TIMEZONE_HEADER } from "./userTimezone";

/**
 * How long to wait for response HEADERS before giving up. Not a whole-request
 * budget: the timer is cleared the moment headers arrive, so a streamed agent
 * turn keeps its socket open for as long as it needs.
 */
const HEADER_TIMEOUT_MS = 30_000;

const SESSION_KEY = "session:expired";
const NETWORK_KEY = "session:unreachable";

/**
 * The app had no global 401 handling: `apiFetch` retried once and, if the
 * refresh failed, handed the 401 back to callers that mostly never inspect the
 * status. The user stayed on the page with a dead token, clicking things that
 * quietly did nothing.
 *
 * Only reached when the caller actually held a token, so the anonymous public
 * share reader — which handles its own 401 explicitly — is not told its session
 * expired when it never had one.
 */
function reportSessionExpired(): void {
  toast.once(SESSION_KEY, () => ({
    title: i18n.t("common:session.expiredTitle"),
    body: i18n.t("common:session.expiredBody"),
    tone: "danger",
    durationMs: null,
    banner: true,
    action: {
      label: i18n.t("common:session.signIn"),
      onClick: () => {
        window.location.assign("/app/login");
      },
    },
  }));
}

function reportUnreachable(): void {
  toast.once(NETWORK_KEY, () => ({
    title: i18n.t("common:session.networkTitle"),
    body: i18n.t("common:session.networkBody", {
      seconds: Math.round(HEADER_TIMEOUT_MS / 1000),
    }),
    tone: "warning",
    durationMs: null,
  }));
}

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
  /** Set when the agent runs outside AgentLayer's planner loop (e.g. ``qwen_code``). */
  external_runtime?: string | null;
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

export type ChatContextBudget = {
  prep_enabled?: boolean;
  budget_from?: string;
  soft_limit_ratio?: number;
  hard_limit_ratio?: number;
  fallback_budget_tokens?: number | null;
  max_messages?: number;
  compaction_enabled?: boolean;
  agent_loop_trim_enabled?: boolean;
};

export type ChatContextMeta = {
  provider_prompt_tokens?: number;
  budget_tokens?: number;
  context_window_tokens?: number;
  budget_source?: string | null;
  soft_limit_tokens?: number;
  hard_limit_tokens?: number;
  soft_limit_ratio?: number;
  hard_limit_ratio?: number;
  messages_in_prompt?: number;
  messages_dropped?: number;
  messages_compacted_this_run?: number;
  messages_capped?: number;
  compaction_applied?: boolean;
  loop_compaction_applied?: boolean;
  summary_active?: boolean;
  summary_covers_messages?: number;
  at_soft_limit?: boolean;
  at_hard_limit?: boolean;
  tool_rounds_dropped?: number;
};

export type ChatRuntimePayload = {
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
  context?: ChatContextBudget;
  /** Resolved window/soft/hard for ``model`` (provider catalog / overrides). */
  context_budget?: Pick<
    ChatContextMeta,
    "context_window_tokens" | "soft_limit_tokens" | "hard_limit_tokens" | "budget_source"
  > | null;
  vision?: {
    available: boolean;
    model?: string | null;
    catalog_owned_by?: string | null;
    reason?: string;
  };
  external_runtimes?: {
    enabled: boolean;
    fallback_internal?: boolean;
    runtimes: Array<{
      id: string;
      available: boolean;
      /** Why the runtime cannot run right now (missing binary, flag off). */
      reason: string;
      supports_resume: boolean;
      supports_write: boolean;
      default_permission_mode: string;
    }>;
    error?: string;
  };
  conversation_goal?: {
    goal: ConversationGoal | null;
    todos: ConversationTodo[];
    plan_mode?: boolean;
  } | null;
};

export type ConversationGoal = {
  id: string;
  revision: number;
  objective: string;
  phase: "active" | "paused" | "completed" | "blocked";
  rounds_started?: number;
  max_goal_rounds?: number;
  blocked_reason?: string | null;
};

export type ConversationTodo = {
  content: string;
  status: "pending" | "in_progress" | "completed";
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

export type FetchChatRuntimeOpts = {
  workspaceId?: string | null;
  model?: string | null;
  modelCatalogOwnedBy?: string | null;
  conversationId?: string | null;
};

export async function fetchChatRuntime(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  opts?: string | null | FetchChatRuntimeOpts
): Promise<ChatRuntimePayload | null> {
  const o: FetchChatRuntimeOpts =
    typeof opts === "string" || opts == null
      ? { workspaceId: opts ?? null }
      : (opts ?? {});
  const params = new URLSearchParams();
  const wid = typeof o.workspaceId === "string" ? o.workspaceId.trim() : "";
  if (wid) params.set("workspace_id", wid);
  const model = typeof o.model === "string" ? o.model.trim() : "";
  if (model) params.set("model", model);
  const owned = typeof o.modelCatalogOwnedBy === "string" ? o.modelCatalogOwnedBy.trim() : "";
  if (owned) params.set("model_catalog_owned_by", owned);
  const cid = typeof o.conversationId === "string" ? o.conversationId.trim() : "";
  if (cid) params.set("conversation_id", cid);
  const qs = params.toString();
  const r = await apiFetch(`/v1/chat/runtime${qs ? `?${qs}` : ""}`, auth);
  if (!r.ok) return null;
  return r.json() as Promise<ChatRuntimePayload>;
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
  semantic_index_enabled?: boolean;
  retrieval_enabled?: boolean;
  docs_rag_enabled?: boolean;
  last_docs_rag_at?: string | null;
  last_docs_rag_stats?: {
    files_ingested?: number;
    chunk_count_total?: number;
    purge_deleted_documents?: number;
  } | null;
  last_docs_rag_error?: string | null;
  last_index_at?: string | null;
  last_index_stats?: {
    total_symbols?: number;
    total_files?: number;
    qdrant_indexed?: number;
    neo4j_edges?: number;
    elapsed_sec?: number;
    scan?: Record<string, unknown>;
    docs_rag?: Record<string, unknown>;
  } | null;
  last_index_error?: string | null;
  index_on_write?: string | null;
  graph_index_enabled?: boolean;
  retrieve_context_sources?: string[] | null;
  tenant_id?: number | null;
  /** ``tenant`` rows are listed under "company"; anything else is private. */
  visibility?: "private" | "tenant";
};

export type WorkspaceListScope = "mine" | "company";

export type WorkspaceListResponse = {
  workspaces?: WorkspaceApiRecord[];
  scope?: WorkspaceListScope;
  tenant_id?: number | null;
};

export type WorkspaceIndexJob = {
  status?: "running" | "done" | "failed";
  phase?: string | null;
  files_done?: number | null;
  files_total?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

export type WorkspaceIndexStatus = {
  ok: boolean;
  workspace_id?: string;
  semantic_index_enabled?: boolean;
  retrieval_enabled?: boolean;
  docs_rag_enabled?: boolean;
  last_docs_rag_at?: string | null;
  last_docs_rag_stats?: WorkspaceApiRecord["last_docs_rag_stats"];
  last_docs_rag_error?: string | null;
  last_index_at?: string | null;
  last_index_stats?: WorkspaceApiRecord["last_index_stats"];
  last_index_error?: string | null;
  index_job?: WorkspaceIndexJob | null;
  index_stale?: boolean;
  index_stale_reason?:
    | "never_indexed"
    | "git_head_newer_than_index"
    | "files_changed_since_index"
    | string
    | null;
  index_on_write_effective?: string;
  graph_index_enabled?: boolean;
  files_out_of_date?: number;
  repo_tree?: string[];
  qdrant?: { configured?: boolean; reachable?: boolean | null; error?: string };
  neo4j?: { configured?: boolean; reachable?: boolean | null; error?: string };
  embedding?: { configured?: boolean; enabled?: boolean; embedding_dim?: number };
  coding_enabled?: boolean;
  error?: string;
};

export type WorkspaceIndexMode = "full" | "code" | "docs";

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
 * Authenticated fetch: refresh before JWT expiry (no 401 noise), then one retry on 401.
 * Concurrent refreshes share a single in-flight POST /auth/refresh.
 */
let refreshInFlight: Promise<string | null> | null = null;

export function sharedRefresh(
  refresh: Pick<AuthContextValue, "refresh">["refresh"]
): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = refresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function bearerForRequest(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<string | null> {
  let token = auth.accessToken;
  if (!token) return null;
  if (accessTokenNeedsRefresh(token)) {
    const next = await sharedRefresh(auth.refresh);
    if (next) token = next;
  }
  return token;
}

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
    if (typeof window !== "undefined" && !headers.has(USER_TIMEZONE_HEADER)) {
      headers.set(USER_TIMEZONE_HEADER, detectUserTimezone());
    }

    // A header timeout, not a request timeout. `fetch` resolves as soon as the
    // response headers arrive, and the timer is cleared at that point — so a
    // streaming chat turn that runs for minutes is untouched, while a server
    // that never answers stops hanging. A blanket timeout here would abort
    // long turns and the callers read an AbortError as "the user cancelled",
    // turning a dead backend into a silently missing answer.
    const controller = new AbortController();
    let timedOut = false;
    const outer = init?.signal;
    const onOuter = () => controller.abort();
    if (outer) {
      if (outer.aborted) controller.abort();
      else outer.addEventListener("abort", onOuter, { once: true });
    }
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, HEADER_TIMEOUT_MS);

    try {
      return await fetch(url, {
        ...init,
        credentials: "include",
        headers,
        signal: controller.signal,
      });
    } catch (error) {
      if (timedOut) {
        reportUnreachable();
        throw new Error(i18n.t("common:session.networkTitle"));
      }
      throw error;
    } finally {
      clearTimeout(timer);
      if (outer) outer.removeEventListener("abort", onOuter);
    }
  };

  // Whether the caller had a token at all decides what a 401 means. An
  // anonymous reader of a public share link getting 401 is that endpoint
  // asking for a sign-in, which it handles itself; a token that came back 401
  // after a refresh is a session the user has to be told about.
  const hadToken = Boolean(auth.accessToken);

  let token = await bearerForRequest(auth);
  let res = await run(token);
  if (res.status === 401) {
    const next = await sharedRefresh(auth.refresh);
    if (next) {
      token = next;
      res = await run(next);
    }
    if (res.status === 401 && hadToken) reportSessionExpired();
  }
  // Any answer that is not a 401 means whatever raised those notices has
  // passed: signing in again, or the server coming back.
  if (res.status !== 401) {
    toast.settle(SESSION_KEY);
    toast.settle(NETWORK_KEY);
  }
  return res;
}
