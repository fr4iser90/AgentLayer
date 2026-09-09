import type { AuthContextValue } from "../../auth/AuthContext";
import type { AgentTimelineEntry } from "./agentLogStorage";
import type { AgentTurnLog, UiMessage } from "./chatThreadStorage";
import { newMessageId } from "./chatThreadStorage";
import {
  fetchConversationDetail,
  putConversation,
  putConversationAgentLog,
} from "./conversationsApi";

function assistantMessage(
  content: string,
  prior?: UiMessage | null,
  reasoningContent?: string
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

/** Persist a completed agent turn when ChatPage is not mounted (navigation away). */
export async function persistDetachedAgentCompletion(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  threadId: string,
  content: string,
  agentLog: AgentTimelineEntry[],
  reasoningContent?: string
): Promise<void> {
  const full = await fetchConversationDetail(auth, threadId);
  const prevMsgs = full.messages;
  const last = prevMsgs[prevMsgs.length - 1];
  const trimmed = content.trim();
  const lastText =
    last && typeof last.content === "string"
      ? last.content.trim()
      : last?.content != null
        ? JSON.stringify(last.content).trim()
        : "";
  const alreadySaved = last?.role === "assistant" && lastText === trimmed;
  if (alreadySaved) {
    const reasoning = reasoningContent?.trim();
    if (reasoning && last && !last.reasoningContent) {
      const messages = [
        ...prevMsgs.slice(0, -1),
        { ...last, reasoningContent: reasoning },
      ];
      await putConversation(auth, {
        ...full,
        messages,
        agentLog,
        messageCount: messages.length,
        updatedAt: Date.now(),
      });
      return;
    }
    await putConversationAgentLog(auth, threadId, {
      agentLog,
      turnLogs: full.turnLogs ?? [],
    });
    return;
  }
  const messages = [...prevMsgs, assistantMessage(content, last, reasoningContent)];
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
  agentLog: AgentTimelineEntry[],
  turnLogs: AgentTurnLog[] = []
): Promise<void> {
  if (!agentLog.length) return;
  // agent_log-only: never rewrite messages (avoids wiping a concurrent completion PUT).
  await putConversationAgentLog(auth, threadId, {
    agentLog,
    turnLogs,
  });
}
