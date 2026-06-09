import { memo, useMemo } from "react";
import { activityForTurn } from "./agentLogStorage";
import type { ChatThread } from "./chatThreadStorage";
import { ChatAgentActivityPanel } from "./ChatAgentActivityPanel";
import { useAgentLiveLog, useAgentWaitHint, type LiveTurnStore } from "./useAgentLiveTurn";

type Props = {
  store: LiveTurnStore;
  activeThread: ChatThread | null;
  selectedTurnId: string | null;
  loading: boolean;
  emptyHint?: string;
  showSubagentToggle?: boolean;
  showSubagents?: boolean;
  onShowSubagentsChange?: (show: boolean) => void;
};

/** Activity panel wired to live-turn log store (isolated re-renders). */
export const ChatLiveActivityPanel = memo(function ChatLiveActivityPanel({
  store,
  activeThread,
  selectedTurnId,
  loading,
  emptyHint,
  showSubagentToggle,
  showSubagents,
  onShowSubagentsChange,
}: Props) {
  const liveLog = useAgentLiveLog(store);
  const waitHint = useAgentWaitHint(store);

  const entries = useMemo(() => {
    if (!activeThread) return [];
    const view =
      store.isActive() && loading
        ? { ...activeThread, agentLog: liveLog }
        : activeThread;
    return activityForTurn(view, selectedTurnId);
  }, [activeThread, selectedTurnId, liveLog, store, loading]);

  return (
    <ChatAgentActivityPanel
      entries={entries}
      loading={loading}
      loadingHint={waitHint}
      emptyHint={emptyHint}
      showSubagentToggle={showSubagentToggle}
      showSubagents={showSubagents}
      onShowSubagentsChange={onShowSubagentsChange}
    />
  );
});
