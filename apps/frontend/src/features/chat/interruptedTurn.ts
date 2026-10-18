import { appendTimelineEntry } from "./agentLogStorage";
import {
  newMessageId,
  type AgentTimelineEntry,
  type ChatThread,
  type UiMessage,
} from "./chatThreadStorage";

export type InterruptTimelineKind =
  | "agent.cancelled"
  | "agent.aborted"
  | "agent.interrupted";

export function isInterruptTimelineKind(kind: string): boolean {
  return (
    kind === "agent.cancelled" ||
    kind === "agent.aborted" ||
    kind === "agent.interrupted"
  );
}

/** Short bubble badge from an LLM/WS error detail (e.g. HTTP 503 + thermal). */
export function formatInterruptedBadgeLabel(detail: string): string {
  const raw = detail.trim();
  const http = raw.match(/\bHTTP\s+(\d{3})\b/i)?.[1];
  const paren = raw.match(/\(([a-z0-9_.-]+)\)/i)?.[1] ?? "";
  const thermal =
    /temperature|thermal/i.test(raw) || /temperature|thermal/i.test(paren);
  const parts = ["Interrupted"];
  if (http) parts.push(http);
  if (thermal) {
    parts.push("thermal");
  } else if (paren && paren.length <= 48 && paren !== http) {
    parts.push(paren.replace(/_/g, " "));
  }
  return parts.join(" · ");
}

function assistantStub(
  content: string,
  reasoningContent?: string,
  prior?: UiMessage | null
): UiMessage {
  const createdAt =
    prior?.role === "assistant" && prior.createdAt != null ? prior.createdAt : Date.now();
  const msg: UiMessage = {
    role: "assistant",
    content,
    createdAt,
    id: newMessageId(),
  };
  const reasoning = reasoningContent?.trim();
  if (reasoning) msg.reasoningContent = reasoning;
  return msg;
}

function stripTrailingEmptyAssistants(msgs: UiMessage[]): UiMessage[] {
  let out = [...msgs];
  while (out.length > 0) {
    const last = out[out.length - 1]!;
    const visible =
      (last.content ?? "").trim().length > 0 ||
      (last.reasoningContent ?? "").trim().length > 0;
    if (last.role === "assistant" && !visible) {
      out = out.slice(0, -1);
    } else break;
  }
  return out;
}

/**
 * Keep user + partial assistant stream/reasoning and mark the timeline interrupted.
 * Empty assistant stubs are kept so the badge can render after reload.
 */
export function threadWithInterruptedTurn(
  th: ChatThread,
  opts: {
    streamText: string;
    streamReasoning?: string;
    logBase: AgentTimelineEntry[];
    kind: InterruptTimelineKind;
    markerText: string;
  }
): ChatThread {
  const agentLog = appendTimelineEntry(opts.logBase, {
    kind: opts.kind,
    text: opts.markerText,
  });
  let messages = stripTrailingEmptyAssistants(th.messages);
  const last = messages[messages.length - 1];
  const streamText = opts.streamText;
  const streamReasoning = opts.streamReasoning?.trim() || "";
  if (last?.role === "assistant") {
    const merged: UiMessage = {
      ...last,
      content: streamText || last.content,
      ...(streamReasoning || last.reasoningContent
        ? { reasoningContent: streamReasoning || last.reasoningContent }
        : {}),
    };
    messages = [...messages.slice(0, -1), merged];
  } else {
    messages = [
      ...messages,
      assistantStub(streamText, streamReasoning || undefined),
    ];
  }
  return {
    ...th,
    messages,
    agentLog,
    messageCount: messages.length,
    updatedAt: Date.now(),
  };
}
