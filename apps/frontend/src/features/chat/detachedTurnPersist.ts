import type { AuthContextValue } from "../../auth/AuthContext";
import type { AgentTimelineEntry } from "./agentLogStorage";
import type { UiMessage } from "./chatThreadStorage";
import { fetchConversationDetail, putConversation } from "./conversationsApi";

function assistantMessage(content: string, prior?: UiMessage | null): UiMessage {
  const createdAt =
    prior?.role === "assistant" && prior.createdAt != null ? prior.createdAt : Date.now();
  return { role: "assistant", content, createdAt };
}

/** Persist a completed agent turn when ChatPage is not mounted (navigation away). */
export async function persistDetachedAgentCompletion(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  threadId: string,
  content: string,
  agentLog: AgentTimelineEntry[]
): Promise<void> {
  const full = await fetchConversationDetail(auth, threadId);
  const prevMsgs = full.messages;
  const messages = [...prevMsgs, assistantMessage(content, prevMsgs[prevMsgs.length - 1])];
  await putConversation(auth, {
    ...full,
    messages,
    agentLog,
    messageCount: messages.length,
    updatedAt: Date.now(),
  });
}

/** Persist in-flight agent activity log when the chat page is not mounted. */
export async function persistDetachedAgentLog(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  threadId: string,
  agentLog: AgentTimelineEntry[]
): Promise<void> {
  if (!agentLog.length) return;
  const full = await fetchConversationDetail(auth, threadId);
  await putConversation(auth, {
    ...full,
    agentLog,
    updatedAt: Date.now(),
  });
}
