import type { AgentTimelineEntry } from "./chatThreadStorage";

export type ContextCompactedWs = {
  phase?: string;
  reason?: string;
  round?: number;
  provider_prompt_tokens?: number;
  soft_limit_tokens?: number;
  context_window_tokens?: number;
  tool_rounds_dropped?: number;
  budget_source?: string;
  summary_active?: boolean;
  messages_dropped?: number;
  messages_compacted_this_run?: number;
  summary_covers_messages?: number;
};

function formatTok(n: number | undefined): string {
  if (n == null || n <= 0) return "—";
  return n.toLocaleString();
}

function resolveMessagesCompacted(msg: ContextCompactedWs): number | undefined {
  const thisRun = msg.messages_compacted_this_run;
  if (thisRun != null && thisRun > 0) return thisRun;
  const dropped = msg.messages_dropped;
  if (dropped != null && dropped > 0) return dropped;
  const covers = msg.summary_covers_messages;
  if (covers != null && covers > 0) return covers;
  return undefined;
}

/** Build timeline row + display text for a compaction WebSocket event. */
export function compactionEventToTimeline(
  msg: ContextCompactedWs
): { kind: "compaction_done"; text: string; extras: Omit<AgentTimelineEntry, "id" | "kind" | "text"> } {
  const phase = msg.phase === "history" ? "history" : "loop";
  const prompt = msg.provider_prompt_tokens;
  const soft = msg.soft_limit_tokens;
  const window = msg.context_window_tokens;
  const dropped = msg.tool_rounds_dropped ?? 0;
  const messagesCompacted = phase === "history" ? resolveMessagesCompacted(msg) : undefined;

  const parts: string[] = [];
  if (phase === "loop") {
    if (prompt != null && prompt > 0 && soft != null) {
      parts.push(`${formatTok(prompt)} / ${formatTok(soft)} soft tok`);
    }
    if (dropped > 0) {
      parts.push(`${dropped} tool round${dropped === 1 ? "" : "s"} → summary`);
    }
    if (msg.round != null && msg.round > 0) {
      parts.push(`after LLM round ${msg.round}`);
    }
    if (window != null && window > 0) {
      parts.push(`window ${formatTok(window)}`);
    }
  } else {
    parts.push("older chat turns → summary");
    if (messagesCompacted != null) {
      parts.push(`${messagesCompacted} message${messagesCompacted === 1 ? "" : "s"} compacted`);
    }
    if (window != null && window > 0) {
      parts.push(`window ${formatTok(window)}`);
    }
  }
  if (msg.budget_source) {
    parts.push(`budget: ${msg.budget_source}`);
  }

  return {
    kind: "compaction_done",
    text: parts.join(" · ") || (phase === "history" ? "History compacted" : "Context compacted"),
    extras: {
      compactionPhase: phase,
      providerPromptTokens: phase === "loop" && prompt != null && prompt > 0 ? prompt : undefined,
      softLimitTokens: phase === "loop" ? soft : undefined,
      contextWindowTokens: window,
      toolRoundsDropped: dropped > 0 ? dropped : undefined,
      budgetSource: msg.budget_source,
      toolRound: msg.round,
      messagesCompacted,
    },
  };
}
