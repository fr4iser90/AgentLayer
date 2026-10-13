import type { UiMessage } from "./chatThreadStorage";

/** Parse API ``created_at`` (ISO string) to Unix ms for UI state. */
export function parseMessageCreatedAt(raw: unknown): number | undefined {
  if (raw == null) return undefined;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw > 1e12 ? raw : raw * 1000;
  }
  if (typeof raw === "string" && raw.trim()) {
    const t = Date.parse(raw);
    return Number.isFinite(t) ? t : undefined;
  }
  return undefined;
}

/** Serialize UI timestamp for conversation API payloads. */
export function messageCreatedAtToApi(ms: number | undefined): string | undefined {
  if (ms == null || !Number.isFinite(ms)) return undefined;
  return new Date(ms).toISOString();
}

export function formatMessageTime(ms: number | undefined): string | null {
  if (ms == null || !Number.isFinite(ms)) return null;
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

type ApiMessageRow = {
  role?: string;
  content?: unknown;
  created_at?: unknown;
  id?: unknown;
  client_message_id?: unknown;
  reasoning?: unknown;
  reasoning_content?: unknown;
};

export function apiMessageToUi(m: ApiMessageRow): UiMessage {
  const role = m.role === "assistant" || m.role === "user" ? m.role : "user";
  const content =
    typeof m.content === "string"
      ? m.content
      : m.content != null
        ? JSON.stringify(m.content)
        : "";
  const createdAt = parseMessageCreatedAt(m.created_at);
  const idRaw = m.id ?? m.client_message_id;
  const id = typeof idRaw === "string" && idRaw.trim() ? idRaw.trim() : undefined;
  const reasoningRaw = m.reasoning ?? m.reasoning_content;
  const reasoningContent =
    typeof reasoningRaw === "string" && reasoningRaw.trim() ? reasoningRaw.trim() : undefined;
  const out: UiMessage = { role, content };
  if (createdAt != null) out.createdAt = createdAt;
  if (id) out.id = id;
  if (reasoningContent) out.reasoningContent = reasoningContent;
  return out;
}

export function uiMessageToApiPayload(
  m: UiMessage,
  serializeContent: (content: string) => string | unknown[]
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    role: m.role,
    content: serializeContent(m.content),
  };
  const iso = messageCreatedAtToApi(m.createdAt);
  if (iso) out.created_at = iso;
  if (m.id?.trim()) {
    out.id = m.id.trim();
    out.client_message_id = m.id.trim();
  }
  const reasoning = m.reasoningContent?.trim();
  if (reasoning) out.reasoning = reasoning;
  return out;
}

/**
 * Stable display times for legacy rows without ``created_at``.
 * Spreads between conversation start and last update (does not use live clock).
 */
export function inferMissingMessageTimestamps(
  messages: UiMessage[],
  conversationCreatedAt: number,
  conversationUpdatedAt: number
): UiMessage[] {
  if (messages.length === 0) return messages;
  if (!messages.some((m) => m.createdAt == null)) return messages;
  const end = Number.isFinite(conversationUpdatedAt) ? conversationUpdatedAt : Date.now();
  const start = Number.isFinite(conversationCreatedAt) ? conversationCreatedAt : end;
  const n = messages.length;
  const span = Math.max(end - start, (n - 1) * 1000);
  const step = n > 1 ? span / (n - 1) : 0;
  return messages.map((m, i) => {
    if (m.createdAt != null) return m;
    return { ...m, createdAt: Math.round(start + step * i) };
  });
}
