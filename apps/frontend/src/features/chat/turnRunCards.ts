import { activityForTurn } from "./agentLogStorage";
import type { AgentTimelineEntry, ChatThread, UiMessage } from "./chatThreadStorage";

/** User turn id that owns this assistant message (walk backward to previous user). */
export function userTurnIdBeforeAssistant(
  messages: UiMessage[],
  assistantIndex: number
): string | null {
  for (let j = assistantIndex - 1; j >= 0; j--) {
    const m = messages[j];
    if (m.role === "user") {
      const id = m.id?.trim();
      return id || null;
    }
  }
  return null;
}

export function timelineForTurn(
  thread: Pick<ChatThread, "messages" | "agentLog" | "turnLogs"> | null,
  turnId: string | null
): AgentTimelineEntry[] {
  if (!thread || !turnId) return [];
  return activityForTurn(thread, turnId);
}
