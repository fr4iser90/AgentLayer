export const NEW_CHAT_TITLE = "New chat";

export type ChatMode = "chat" | "agent";

/** ``web`` = first-party UI; otherwise bridge provider id from the server (e.g. telegram, slack). */
export type ChatSource = string;

export type UiMessage = {
  role: "user" | "assistant";
  content: string;
  id?: string;
  createdAt?: number;
};

export type AgentTimelineEntry = {
  id: string;
  kind: string;
  text: string;
  toolName?: string;
  durationMs?: number;
  resultChars?: number;
};

export type AgentTurnLog = {
  userMessageId: string;
  entries: AgentTimelineEntry[];
};

export type ChatThread = {
  id: string;
  title: string;
  mode: ChatMode;
  model: string;
  /** Opaque provider id from the selected GET /v1/models row (``owned_by``); must match the dropdown choice. */
  modelProvider?: string;
  messages: UiMessage[];
  /** Current turn agent timeline (live). */
  agentLog?: AgentTimelineEntry[];
  /** Archived activity per user prompt. */
  turnLogs?: AgentTurnLog[];
  updatedAt: number;
  /** Conversation row ``created_at`` from server (ms); used to infer legacy message times. */
  conversationCreatedAt?: number;
  /** Set when this thread is the dashboard-scoped assistant chat (server-side). */
  dashboardId?: string;
  /** Shared dashboard thread (members see same messages). */
  shared?: boolean;
  /** Origin: first-party ``web`` or bridge provider id. */
  source?: ChatSource;
  /** Last composer agent (registry id); persisted with conversation. */
  agentId?: string | null;
  /** Last composer workspace (project_workspaces id); persisted with conversation. */
  workspaceId?: string | null;
  /** Server list field ``message_count``; falls back to ``messages.length`` when loaded. */
  messageCount?: number;
};

export type PersistedState = {
  version: 1;
  activeThreadId: string | null;
  threads: ChatThread[];
};

const STORAGE_PREFIX = "agent-layer.chat.v1";

function keyForUser(userId: string): string {
  return `${STORAGE_PREFIX}:${userId}`;
}

export function newMessageId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `m-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Ensure every message has a stable id (for scroll / turn navigation). */
export function ensureMessageIds(messages: UiMessage[]): UiMessage[] {
  return messages.map((m) => (m.id ? m : { ...m, id: newMessageId() }));
}

export function titleFromFirstMessage(userText: string, maxLen = 52): string {
  let raw = userText.replace(/\s+/g, " ").trim();
  if (raw.startsWith("[")) {
    try {
      const p = JSON.parse(userText) as Array<{ type?: string; text?: string }>;
      if (Array.isArray(p)) {
        const tx = p.find((x) => x.type === "text" && x.text)?.text;
        if (tx) raw = tx.replace(/\s+/g, " ").trim();
        else if (p.some((x) => x.type === "image_url")) raw = "Image";
      }
    } catch {
      /* use raw string */
    }
  }
  if (!raw) return NEW_CHAT_TITLE;
  if (raw.length <= maxLen) return raw;
  return `${raw.slice(0, maxLen - 1)}…`;
}

export function loadThreads(userId: string): PersistedState | null {
  try {
    const raw = localStorage.getItem(keyForUser(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedState;
    if (parsed?.version !== 1 || !Array.isArray(parsed.threads)) return null;
    for (const th of parsed.threads) {
      const legacy = (th as { modelCatalogOwnedBy?: string }).modelCatalogOwnedBy;
      if (legacy && !th.modelProvider) th.modelProvider = legacy;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveThreads(userId: string, state: PersistedState): void {
  try {
    localStorage.setItem(keyForUser(userId), JSON.stringify(state));
  } catch {
    /* quota or private mode */
  }
}

export function newThread(modelFallback: string): ChatThread {
  const id =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `t-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const now = Date.now();
  return {
    id,
    title: NEW_CHAT_TITLE,
    mode: "chat",
    model: modelFallback,
    messages: [],
    agentLog: [],
    turnLogs: [],
    updatedAt: now,
  };
}

export function exportThreadJson(thread: ChatThread): string {
  return JSON.stringify(
    {
      exportedAt: new Date().toISOString(),
      thread,
    },
    null,
    2
  );
}
