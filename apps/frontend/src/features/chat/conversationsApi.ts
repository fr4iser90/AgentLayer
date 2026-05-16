import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type {
  AgentTimelineEntry,
  ChatMode,
  ChatSource,
  ChatThread,
  UiMessage,
} from "./chatThreadStorage";
import { normalizeCatalogRoutingToken } from "../../lib/modelCatalog";
import { normalizeServerContent } from "./messageFormat";

function modelProviderFromApi(item: Record<string, unknown>): string | undefined {
  const raw = item.model_catalog_owned_by;
  if (typeof raw !== "string" || !raw.trim()) return undefined;
  return normalizeCatalogRoutingToken(raw);
}

type ApiMessage = { role: "user" | "assistant" | "system"; content: unknown };

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
  };
}

/** Prefer server ``model_catalog_owned_by``; keep local only when server has none yet. */
export function mergeServerThreadWithLocal(
  server: ChatThread,
  local: ChatThread | undefined
): ChatThread {
  if (!local || local.id !== server.id) return server;
  if (server.modelProvider) return server;
  if (local.modelProvider) return { ...server, modelProvider: local.modelProvider };
  return server;
}

export function mapServerToThread(raw: Record<string, unknown>): ChatThread {
  const messages = Array.isArray(raw.messages)
    ? (raw.messages as ApiMessage[]).map((m) => {
        const c = (m as { content?: unknown }).content;
        return {
          role: m.role === "assistant" || m.role === "user" ? m.role : "user",
          content: normalizeServerContent(c),
        };
      })
    : [];
  const agentLog = Array.isArray(raw.agent_log)
    ? (raw.agent_log as AgentTimelineEntry[])
    : [];
  const ws = raw.dashboard_id;
  const src = normalizeSource(raw.source);
  return {
    id: String(raw.id ?? ""),
    title: typeof raw.title === "string" ? raw.title : "",
    mode: raw.mode === "agent" ? "agent" : "chat",
    model: typeof raw.model === "string" ? raw.model : "",
    messages,
    agentLog,
    updatedAt: Date.parse(String(raw.updated_at ?? Date.now())) || Date.now(),
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
    agent_log: AgentTimelineEntry[];
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
      messages: body.messages.map((m) => ({ role: m.role, content: serializeMessageContent(m.content) })),
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
  if (!r.ok) throw new Error("failed to create conversation");
  return mapServerToThread(data.conversation ?? {});
}

export async function putConversation(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  thread: ChatThread
) {
  const r = await apiFetch(`/v1/user/conversations/${encodeURIComponent(thread.id)}`, auth, {
    method: "PUT",
    body: JSON.stringify({
      title: thread.title,
      mode: thread.mode,
      model: thread.model,
      messages: thread.messages.map((m) => ({
        role: m.role,
        content: serializeMessageContent(m.content),
      })),
      agent_log: thread.agentLog ?? [],
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
