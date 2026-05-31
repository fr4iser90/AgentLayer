import { memo } from "react";
import { AgentActivityPanel } from "./AgentActivityPanel";
import type { AgentTimelineEntry } from "./chatThreadStorage";

type Props = {
  entries: AgentTimelineEntry[];
  loading?: boolean;
  emptyHint?: string;
  showSubagentToggle?: boolean;
  showSubagents?: boolean;
  onShowSubagentsChange?: (show: boolean) => void;
};

/** Isolated activity panel so live-turn log ticks do not re-render the full chat page. */
export const ChatAgentActivityPanel = memo(function ChatAgentActivityPanel({
  entries,
  loading,
  emptyHint,
  showSubagentToggle,
  showSubagents,
  onShowSubagentsChange,
}: Props) {
  return (
    <AgentActivityPanel
      entries={entries}
      loading={loading}
      emptyHint={emptyHint}
      layout="header"
      className="min-h-0 w-full"
      showSubagentToggle={showSubagentToggle}
      showSubagents={showSubagents}
      onShowSubagentsChange={onShowSubagentsChange}
    />
  );
});
