/**
 * Chat UX performance samples (hydrate, thread switch, TTFD, poll lag, turn latency).
 *
 * Enable:
 * - Dev: on by default
 * - Prod: ``localStorage.setItem("agentlayer:chat-perf", "1")`` then reload
 * - Or ``?chatPerf=1`` in the URL once
 *
 * Inspect: ``window.__agentlayerChatPerf.dump()`` / ``.clear()``
 */

export type ChatPerfKind =
  | "conversations_list"
  | "conversation_detail"
  | "thread_switch"
  | "hydrate"
  | "send_to_first_delta"
  | "poll_to_assistant"
  | "turn_latency";

export type ChatPerfSample = {
  kind: ChatPerfKind;
  ms: number;
  at: number;
  meta?: Record<string, string | number | boolean | null | undefined>;
};

const STORAGE_KEY = "agentlayer:chat-perf";
const MAX_SAMPLES = 80;

let samples: ChatPerfSample[] = [];
const pending = new Map<string, number>();

function queryEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (new URLSearchParams(window.location.search).get("chatPerf") === "1") return true;
  } catch {
    /* ignore */
  }
  try {
    if (window.localStorage.getItem(STORAGE_KEY) === "1") return true;
  } catch {
    /* ignore */
  }
  try {
    // Vite injects import.meta.env.DEV; absent in plain Node.
    const env = (import.meta as ImportMeta & { env?: { DEV?: boolean } }).env;
    return Boolean(env?.DEV);
  } catch {
    return false;
  }
}

export function chatPerfEnabled(): boolean {
  return queryEnabled();
}

export function chatPerfMarkStart(key: string): void {
  pending.set(key, performance.now());
}

export function chatPerfMarkEnd(
  key: string,
  kind: ChatPerfKind,
  meta?: ChatPerfSample["meta"]
): number | null {
  const start = pending.get(key);
  pending.delete(key);
  if (start == null) return null;
  return chatPerfRecord(kind, performance.now() - start, meta);
}

export function chatPerfRecord(
  kind: ChatPerfKind,
  ms: number,
  meta?: ChatPerfSample["meta"]
): number {
  const rounded = Math.round(ms * 10) / 10;
  const sample: ChatPerfSample = { kind, ms: rounded, at: Date.now(), meta };
  samples.push(sample);
  if (samples.length > MAX_SAMPLES) samples = samples.slice(-MAX_SAMPLES);
  if (chatPerfEnabled()) {
    // eslint-disable-next-line no-console
    console.info("[chat-perf]", kind, `${rounded}ms`, meta ?? {});
  }
  return rounded;
}

export async function chatPerfTimeAsync<T>(
  kind: ChatPerfKind,
  meta: ChatPerfSample["meta"] | undefined,
  fn: () => Promise<T>
): Promise<T> {
  const t0 = performance.now();
  try {
    return await fn();
  } finally {
    chatPerfRecord(kind, performance.now() - t0, meta);
  }
}

/** Pending keys for send→first delta / poll / turn (one active turn). */
export function chatPerfBeginTurn(threadId: string, userMsgId: string): void {
  const id = `${threadId}:${userMsgId}`;
  chatPerfMarkStart(`ttfd:${id}`);
  chatPerfMarkStart(`turn:${id}`);
}

export function chatPerfNoteFirstDelta(threadId: string, userMsgId: string): void {
  const id = `${threadId}:${userMsgId}`;
  chatPerfMarkEnd(`ttfd:${id}`, "send_to_first_delta", { threadId, userMsgId });
}

export function chatPerfBeginPoll(threadId: string, reason: string): void {
  chatPerfMarkStart(`poll:${threadId}`);
  if (chatPerfEnabled()) {
    // eslint-disable-next-line no-console
    console.info("[chat-perf]", "poll_start", { threadId, reason });
  }
}

export function chatPerfNotePollAssistant(threadId: string): void {
  chatPerfMarkEnd(`poll:${threadId}`, "poll_to_assistant", { threadId });
}

export function chatPerfEndTurn(
  threadId: string,
  userMsgId: string,
  meta?: ChatPerfSample["meta"]
): void {
  const id = `${threadId}:${userMsgId}`;
  // Drop unused TTFD mark if stream never produced a delta (tools-only / error).
  if (pending.has(`ttfd:${id}`)) pending.delete(`ttfd:${id}`);
  chatPerfMarkEnd(`turn:${id}`, "turn_latency", { threadId, userMsgId, ...meta });
}

export function chatPerfDump(): ChatPerfSample[] {
  return [...samples];
}

export function chatPerfClear(): void {
  samples = [];
  pending.clear();
}

export function chatPerfSummary(): Record<ChatPerfKind, { n: number; avgMs: number; maxMs: number }> {
  const out = {} as Record<ChatPerfKind, { n: number; avgMs: number; maxMs: number }>;
  for (const s of samples) {
    const cur = out[s.kind] ?? { n: 0, avgMs: 0, maxMs: 0 };
    const n = cur.n + 1;
    const avgMs = (cur.avgMs * cur.n + s.ms) / n;
    out[s.kind] = { n, avgMs: Math.round(avgMs * 10) / 10, maxMs: Math.max(cur.maxMs, s.ms) };
  }
  return out;
}

declare global {
  interface Window {
    __agentlayerChatPerf?: {
      enabled: () => boolean;
      dump: () => ChatPerfSample[];
      summary: () => ReturnType<typeof chatPerfSummary>;
      clear: () => void;
    };
  }
}

export function installChatPerfConsole(): void {
  if (typeof window === "undefined") return;
  window.__agentlayerChatPerf = {
    enabled: chatPerfEnabled,
    dump: chatPerfDump,
    summary: chatPerfSummary,
    clear: chatPerfClear,
  };
}
