import { memo, useMemo } from "react";
import { activityForTurn } from "./agentLogStorage";
import type { ChatThread } from "./chatThreadStorage";
import { AssistantTurnBlock } from "./AssistantTurnBlock";
import type { AuthContextValue } from "../../auth/AuthContext";
import type { Proposal, ProposalOption } from "../../lib/proposalParser";
import {
  useAgentLiveLog,
  useAgentStreamText,
  type LiveTurnStore,
} from "./useAgentLiveTurn";

type Props = {
  store: LiveTurnStore;
  activeThread: ChatThread | null;
  latestTurnId: string | null;
  runStartedAtMs: number | null;
  auth: AuthContextValue;
  selectedByProposalId: Map<string, string | null>;
  onSelectProposalOption: (proposal: Proposal, option: ProposalOption) => void;
  onSecretSaved: (promptId: string, serviceKey: string) => void;
  expandedRunCardIds: ReadonlySet<string>;
  onToggleRunCardExpanded: (cardId: string) => void;
};

/** In-flight assistant bubble: subscribes to stream/log store (no full ChatPage re-render). */
export const ChatInFlightAssistantTurn = memo(function ChatInFlightAssistantTurn({
  store,
  activeThread,
  latestTurnId,
  runStartedAtMs,
  auth,
  selectedByProposalId,
  onSelectProposalOption,
  onSecretSaved,
  expandedRunCardIds,
  onToggleRunCardExpanded,
}: Props) {
  const streamText = useAgentStreamText(store);
  const liveLog = useAgentLiveLog(store);

  const timelineEntries = useMemo(() => {
    if (!activeThread || !latestTurnId) return [];
    return activityForTurn({ ...activeThread, agentLog: liveLog }, latestTurnId);
  }, [activeThread, latestTurnId, liveLog]);

  if (!latestTurnId) return null;

  return (
    <AssistantTurnBlock
      key={`assistant-turn-${latestTurnId}`}
      content={streamText}
      timelineEntries={timelineEntries}
      running
      runStartedAtMs={runStartedAtMs}
      auth={auth}
      selectedByProposalId={selectedByProposalId}
      onSelectProposalOption={onSelectProposalOption}
      onSecretSaved={onSecretSaved}
      expandedRunCardIds={expandedRunCardIds}
      onToggleRunCardExpanded={onToggleRunCardExpanded}
    />
  );
});
