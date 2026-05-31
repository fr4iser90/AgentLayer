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
};

function formatTok(n: number | undefined): string {
  if (n == null || n <= 0) return "—";
  return n.toLocaleString();
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

  const parts: string[] = [];
  if (prompt != null && soft != null) {
    parts.push(`${formatTok(prompt)} / ${formatTok(soft)} soft tok`);
  }
  if (window != null && window > 0) {
    parts.push(`window ${formatTok(window)}`);
  }
  if (phase === "loop" && dropped > 0) {
    parts.push(`${dropped} tool round${dropped === 1 ? "" : "s"} → summary`);
  }
  if (phase === "history") {
    parts.push("older chat turns → summary");
  }
  if (msg.budget_source) {
    parts.push(`budget: ${msg.budget_source}`);
  }
  if (msg.round != null && msg.round > 0) {
    parts.push(`after LLM round ${msg.round}`);
  }

  return {
    kind: "compaction_done",
    text: parts.join(" · ") || (phase === "history" ? "History compacted" : "Context compacted"),
    extras: {
      compactionPhase: phase,
      providerPromptTokens: prompt,
      softLimitTokens: soft,
      contextWindowTokens: window,
      toolRoundsDropped: dropped > 0 ? dropped : undefined,
      budgetSource: msg.budget_source,
      toolRound: msg.round,
    },
  };
}
