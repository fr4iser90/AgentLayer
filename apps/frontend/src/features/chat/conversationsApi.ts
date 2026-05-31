import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type {
  AgentTimelineEntry,
  ChatMode,
  ChatSource,
  ChatThread,
  UiMessage,
} from "./chatThreadStorage";
import {
  assignMissingUserMessageIds,
  mergeAgentLogPreferRicher,
  parseAgentLogPayload,
  serializeAgentLogPayload,
} from "./agentLogStorage";
import { normalizeCatalogRoutingToken } from "../../lib/modelCatalog";
import { normalizeServerContent } from "./messageFormat";
import { apiMessageToUi, inferMissingMessageTimestamps, uiMessageToApiPayload } from "./messageTimestamps";

function modelProviderFromApi(item: Record<string, unknown>): string | undefined {
  const raw = item.model_catalog_owned_by;
  if (typeof raw !== "string" || !raw.trim()) return undefined;
  return normalizeCatalogRoutingToken(raw);
}

type ApiMessage = { role: "user" | "assistant" | "system"; content: unknown; created_at?: unknown };

function apiErrorDetail(err: unknown, fallback: string): string {
  if (!err || typeof err !== "object" || !("detail" in err)) return fallback;
  const d = (err as { detail: unknown }).detail;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d)) {
    const parts = d
      .map((x) => {
        if (x && typeof x === "object" && "msg" in x) return String((x as { msg: unknown }).msg);
        return typeof x === "string" ? x : "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

function serializeMessageContent(content: string): string | unknown[] {
  if (typeof content === "string" && content.trim().startsWith("[")) {
    try {
      const p = JSON.parse(content) as unknown;
      if (Array.isArray(p)) return p;
    } catch {
      /* keep string */
    }
  }
  return content;
}

function normalizeSource(raw: unknown): ChatSource {
  if (typeof raw !== "string") return "web";
  const s = raw.trim().toLowerCase();
  return s || "web";
}

/** List endpoint row (no message bodies). */
export function mapListItemToThread(item: Record<string, unknown>): ChatThread {
  const ws = item.dashboard_id;
  const src = normalizeSource(item.source);
  return {
    id: String(item.id ?? ""),
    title: typeof item.title === "string" ? item.title : "",
    mode: item.mode === "agent" ? "agent" : "chat",
    model: typeof item.model === "string" ? item.model : "",
    messages: [],
    agentLog: [],
    turnLogs: [],
    updatedAt: Date.parse(String(item.updated_at ?? Date.now())) || Date.now(),
    dashboardId: typeof ws === "string" && ws ? ws : undefined,
    shared: typeof item.shared === "boolean" ? item.shared : undefined,
    source: src,
    messageCount: typeof item.message_count === "number" ? item.message_count : undefined,
    ...(typeof item.agent_id === "string" && item.agent_id.trim()
      ? { agentId: item.agent_id.trim() }
      : item.agent_id === null
        ? { agentId: null as string | null }
        : {}),
    ...(typeof item.workspace_id === "string" && item.workspace_id.trim()
      ? { workspaceId: item.workspace_id.trim() }
      : item.workspace_id === null
        ? { workspaceId: null as string | null }
        : {}),
    ...((): { modelProvider?: string } => {
      const prov = modelProviderFromApi(item);
      return prov ? { modelProvider: prov } : {};
    })(),
    ...(typeof item.active_task_id === "string" && item.active_task_id.trim()
      ? { activeTaskId: item.active_task_id.trim() }
      : item.active_task_id === null
        ? { activeTaskId: null as string | null }
        : {}),
  };
}

/** Prefer server fields; keep local ``createdAt`` when server row lacks it (same index). */
export function mergeServerThreadWithLocal(
  server: ChatThread,
  local: ChatThread | undefined
): ChatThread {
  if (!local || local.id !== server.id) return server;
  let merged: ChatThread = server;
  if (!server.modelProvider && local.modelProvider) {
    merged = { ...merged, modelProvider: local.modelProvider };
  }
  if (server.messages.length === local.messages.length) {
    const messages = server.messages.map((sm, i) => {
      if (sm.createdAt != null) return sm;
      const lm = local.messages[i];
      if (lm?.createdAt != null) return { ...sm, createdAt: lm.createdAt };
      return sm;
    });
    merged = { ...merged, messages };
  }
  const agentLogPatch = mergeAgentLogPreferRicher(server, local);
  merged = { ...merged, ...agentLogPatch };
  return merged;
}

export function mapServerToThread(raw: Record<string, unknown>): ChatThread {
  const rawMessages = Array.isArray(raw.messages)
    ? (raw.messages as ApiMessage[]).map((m) => {
        const ui = apiMessageToUi({
          role: m.role,
          content: (m as { content?: unknown }).content,
          created_at: m.created_at,
        });
        return {
          ...ui,
          content: normalizeServerContent(ui.content),
        };
      })
    : [];
  const conversationCreatedAt =
    Date.parse(String(raw.created_at ?? "")) || Date.parse(String(raw.updated_at ?? Date.now())) || Date.now();
  const updatedAt = Date.parse(String(raw.updated_at ?? Date.now())) || Date.now();
  const messages = inferMissingMessageTimestamps(
    assignMissingUserMessageIds(rawMessages),
    conversationCreatedAt,
    updatedAt
  );
  const { agentLog, turnLogs } = parseAgentLogPayload(raw.agent_log);
  const ws = raw.dashboard_id;
  const src = normalizeSource(raw.source);
  return {
    id: String(raw.id ?? ""),
    title: typeof raw.title === "string" ? raw.title : "",
    mode: raw.mode === "agent" ? "agent" : "chat",
    model: typeof raw.model === "string" ? raw.model : "",
    messages,
    agentLog,
    turnLogs,
    updatedAt,
    conversationCreatedAt,
    dashboardId: typeof ws === "string" && ws ? ws : undefined,
    shared: typeof raw.shared === "boolean" ? raw.shared : undefined,
    source: src,
    messageCount: messages.length,
    ...(typeof raw.agent_id === "string" && raw.agent_id.trim()
      ? { agentId: raw.agent_id.trim() }
      : raw.agent_id === null
        ? { agentId: null as string | null }
        : {}),
    ...(typeof raw.workspace_id === "string" && raw.workspace_id.trim()
      ? { workspaceId: raw.workspace_id.trim() }
      : raw.workspace_id === null
        ? { workspaceId: null as string | null }
        : {}),
    ...((): { modelProvider?: string } => {
      const prov = modelProviderFromApi(raw);
      return prov ? { modelProvider: prov } : {};
    })(),
    ...(typeof raw.active_task_id === "string" && raw.active_task_id.trim()
      ? { activeTaskId: raw.active_task_id.trim() }
      : raw.active_task_id === null
        ? { activeTaskId: null as string | null }
        : {}),
    delegateAutoRespondEnabled: raw.delegate_auto_respond_enabled === true,
    delegateAutoRespondAfterSec:
      typeof raw.delegate_auto_respond_after_sec === "number"
        ? raw.delegate_auto_respond_after_sec
        : 60,
    delegateMaxChainTurns:
      typeof raw.delegate_max_chain_turns === "number" ? raw.delegate_max_chain_turns : 3,
  };
}

export async function fetchConversationList(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  opts?: { dashboardId?: string }
) {
  const q =
    opts?.dashboardId && opts.dashboardId.trim()
      ? `?dashboard_id=${encodeURIComponent(opts.dashboardId.trim())}`
      : "";
  const r = await apiFetch(`/v1/user/conversations${q}`, auth);
  const data = (await r.json()) as { conversations?: Record<string, unknown>[] };
  if (!r.ok) throw new Error("failed to list conversations");
  return data.conversations ?? [];
}

export async function fetchConversationDetail(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  id: string
) {
  const r = await apiFetch(`/v1/user/conversations/${encodeURIComponent(id)}`, auth);
  const data = (await r.json()) as { conversation?: Record<string, unknown> };
  if (!r.ok) throw new Error("failed to load conversation");
  return mapServerToThread(data.conversation ?? {});
}

export async function createConversation(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  body: {
    title: string;
    mode: ChatMode;
    model: string;
    messages: UiMessage[];
    agent_log: ReturnType<typeof serializeAgentLogPayload> | AgentTimelineEntry[];
    dashboard_id?: string;
    /** One shared thread per dashboard; all members with access see the same messages. */
    shared?: boolean;
    agent_id?: string | null;
    workspace_id?: string | null;
    model_catalog_owned_by?: string | null;
  }
) {
  const r = await apiFetch("/v1/user/conversations", auth, {
    method: "POST",
    body: JSON.stringify({
      title: body.title,
      mode: body.mode,
      model: body.model,
      messages: body.messages.map((m) => uiMessageToApiPayload(m, serializeMessageContent)),
      agent_log: body.agent_log,
      ...(body.dashboard_id ? { dashboard_id: body.dashboard_id } : {}),
      ...(body.shared ? { shared: true } : {}),
      ...(body.agent_id !== undefined ? { agent_id: body.agent_id } : {}),
      ...(body.workspace_id !== undefined ? { workspace_id: body.workspace_id } : {}),
      ...(body.model_catalog_owned_by !== undefined
        ? { model_catalog_owned_by: body.model_catalog_owned_by }
        : {}),
    }),
  });
  const data = (await r.json()) as { conversation?: Record<string, unknown> };
  if (!r.ok) throw new Error(apiErrorDetail(data, "failed to create conversation"));
  return mapServerToThread(data.conversation ?? {});
}

export async function putConversation(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  thread: ChatThread
): Promise<ChatThread> {
  const r = await apiFetch(`/v1/user/conversations/${encodeURIComponent(thread.id)}`, auth, {
    method: "PUT",
    body: JSON.stringify({
      title: thread.title,
      mode: thread.mode,
      model: thread.model,
      messages: thread.messages.map((m) => uiMessageToApiPayload(m, serializeMessageContent)),
      agent_log: serializeAgentLogPayload(thread),
      ...(thread.agentId !== undefined ? { agent_id: thread.agentId } : {}),
      ...(thread.workspaceId !== undefined ? { workspace_id: thread.workspaceId } : {}),
      ...(thread.modelProvider !== undefined
        ? { model_catalog_owned_by: thread.modelProvider || null }
        : {}),
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(
      err && typeof err === "object" && "detail" in err ? String((err as { detail: unknown }).detail) : "save failed"
    );
  }
  const data = (await r.json()) as { conversation?: Record<string, unknown> };
  const fromServer = mapServerToThread(data.conversation ?? {});
  return mergeServerThreadWithLocal(fromServer, thread);
}

export async function deleteConversationApi(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  id: string
) {
  const r = await apiFetch(`/v1/user/conversations/${encodeURIComponent(id)}`, auth, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error("delete failed");
}
