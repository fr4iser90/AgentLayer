import type { AgentTimelineEntry, AgentTurnLog, ChatThread, UiMessage } from "./chatThreadStorage";
import { newMessageId } from "./chatThreadStorage";

export type AgentLogPayloadV2 = {
  v: 2;
  current: AgentTimelineEntry[];
  turns: AgentTurnLog[];
};

function isTimelineEntry(x: unknown): x is AgentTimelineEntry {
  return (
    !!x &&
    typeof x === "object" &&
    typeof (x as AgentTimelineEntry).id === "string" &&
    typeof (x as AgentTimelineEntry).kind === "string" &&
    typeof (x as AgentTimelineEntry).text === "string"
  );
}

function isTurnLog(x: unknown): x is AgentTurnLog {
  return (
    !!x &&
    typeof x === "object" &&
    typeof (x as AgentTurnLog).userMessageId === "string" &&
    Array.isArray((x as AgentTurnLog).entries)
  );
}

/** Parse server ``agent_log`` field (legacy array or v2 object). */
export function parseAgentLogPayload(raw: unknown): {
  agentLog: AgentTimelineEntry[];
  turnLogs: AgentTurnLog[];
} {
  if (Array.isArray(raw)) {
    const entries = raw.filter(isTimelineEntry);
    return { agentLog: entries, turnLogs: [] };
  }
  if (raw && typeof raw === "object" && (raw as AgentLogPayloadV2).v === 2) {
    const p = raw as AgentLogPayloadV2;
    return {
      agentLog: Array.isArray(p.current) ? p.current.filter(isTimelineEntry) : [],
      turnLogs: Array.isArray(p.turns) ? p.turns.filter(isTurnLog) : [],
    };
  }
  return { agentLog: [], turnLogs: [] };
}

/** Serialize thread agent logs for PUT/POST. */
export function serializeAgentLogPayload(thread: Pick<ChatThread, "agentLog" | "turnLogs">): AgentLogPayloadV2 {
  return {
    v: 2,
    current: thread.agentLog ?? [],
    turns: thread.turnLogs ?? [],
  };
}

/** Activity entries for a selected user message turn. */
export function activityForTurn(
  thread: Pick<ChatThread, "messages" | "agentLog" | "turnLogs">,
  selectedUserMessageId: string | null
): AgentTimelineEntry[] {
  const userMsgs = thread.messages.filter((m) => m.role === "user" && m.id);
  if (userMsgs.length === 0) return thread.agentLog ?? [];

  const latestUserId = userMsgs[userMsgs.length - 1]!.id!;
  const turnId = selectedUserMessageId ?? latestUserId;

  const archived = (thread.turnLogs ?? []).find((t) => t.userMessageId === turnId);
  if (archived) return archived.entries;

  if (turnId === latestUserId) return thread.agentLog ?? [];
  return [];
}

/** Last user message id in thread (with fallback). */
export function latestUserMessageId(thread: Pick<ChatThread, "messages">): string | null {
  const users = thread.messages.filter((m) => m.role === "user");
  const last = users[users.length - 1];
  return last?.id ?? null;
}

/**
 * Before starting a new agent turn: archive current agentLog under the previous user message id.
 * Returns patch fields for the thread.
 */
export function archiveTurnBeforeNewPrompt(
  thread: ChatThread
): Pick<ChatThread, "turnLogs" | "agentLog"> {
  const users = thread.messages.filter((m) => m.role === "user" && m.id);
  const prevUser = users.length > 0 ? users[users.length - 1] : null;
  const currentLog = thread.agentLog ?? [];
  let turnLogs = [...(thread.turnLogs ?? [])];

  if (prevUser?.id && currentLog.length > 0) {
    const idx = turnLogs.findIndex((t) => t.userMessageId === prevUser.id);
    const entry: AgentTurnLog = { userMessageId: prevUser.id, entries: currentLog };
    if (idx >= 0) {
      turnLogs = turnLogs.map((t, i) => (i === idx ? entry : t));
    } else {
      turnLogs = [...turnLogs, entry];
    }
  }

  return {
    turnLogs,
    agentLog: [],
  };
}

export function appendTimelineEntry(
  log: AgentTimelineEntry[],
  entry: Omit<AgentTimelineEntry, "id"> & { id?: string }
): AgentTimelineEntry[] {
  return [
    ...log,
    {
      id: entry.id ?? `${Date.now()}-${log.length}`,
      kind: entry.kind,
      text: entry.text,
      ...(entry.toolName != null ? { toolName: entry.toolName } : {}),
      ...(entry.durationMs != null ? { durationMs: entry.durationMs } : {}),
      ...(entry.resultChars != null ? { resultChars: entry.resultChars } : {}),
      ...(entry.subagentAgentId != null ? { subagentAgentId: entry.subagentAgentId } : {}),
      ...(entry.nested === true ? { nested: true } : {}),
      ...(entry.indexMode != null ? { indexMode: entry.indexMode } : {}),
      ...(entry.indexPhase != null ? { indexPhase: entry.indexPhase } : {}),
      ...(entry.filesDone != null ? { filesDone: entry.filesDone } : {}),
      ...(entry.filesTotal != null ? { filesTotal: entry.filesTotal } : {}),
      ...(entry.runStatus != null ? { runStatus: entry.runStatus } : {}),
      ...(entry.streamOffset != null && entry.streamOffset >= 0
        ? { streamOffset: entry.streamOffset }
        : {}),
      ...(entry.secretPrompt != null ? { secretPrompt: entry.secretPrompt } : {}),
    },
  ];
}

/** Mark a secret prompt card as saved in agentLog and archived turnLogs. */
export function markSecretPromptSaved(
  thread: Pick<ChatThread, "agentLog" | "turnLogs">,
  promptId: string
): Pick<ChatThread, "agentLog" | "turnLogs"> {
  const patch = (entries: AgentTimelineEntry[]): AgentTimelineEntry[] =>
    entries.map((e) =>
      e.secretPrompt?.promptId === promptId
        ? { ...e, secretPrompt: { ...e.secretPrompt!, status: "saved" as const } }
        : e
    );
  return {
    agentLog: patch(thread.agentLog ?? []),
    turnLogs: (thread.turnLogs ?? []).map((t) => ({
      ...t,
      entries: patch(t.entries),
    })),
  };
}

/** Assign ids to user messages missing them (e.g. after server load). */
export function assignMissingUserMessageIds(messages: UiMessage[]): UiMessage[] {
  return messages.map((m) => {
    if (m.role === "user" && !m.id) return { ...m, id: newMessageId() };
    return m;
  });
}
