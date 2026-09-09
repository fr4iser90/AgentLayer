import { useEffect, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getAgentChatSession } from "./agentChatSession";
import { useAgentWaitHint } from "./useAgentLiveTurn";

function useActiveAgentTurn() {
  const session = getAgentChatSession();
  return useSyncExternalStore(
    session.subscribe,
    session.getActiveTurn,
    () => null
  );
}

/**
 * Global header chip: visible while an agent turn runs, including after navigating
 * away from Chat. Links back to the active conversation.
 */
export function AgentRunningBadge() {
  const { t } = useTranslation();
  const turn = useActiveAgentTurn();
  const session = getAgentChatSession();
  const waitHint = useAgentWaitHint(session.liveTurn);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!turn) {
      setElapsedSec(0);
      return;
    }
    const tick = () => {
      setElapsedSec(Math.max(0, Math.floor((Date.now() - turn.startedAtMs) / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [turn]);

  if (!turn) return null;

  const href = `/chat?c=${encodeURIComponent(turn.threadId)}`;
  const label = waitHint?.trim()
    ? waitHint.trim()
    : t("chat:thinkingBadge");
  const timeLabel =
    elapsedSec >= 60
      ? t("chat:thinkingBadgeElapsedMin", { min: Math.floor(elapsedSec / 60), sec: elapsedSec % 60 })
      : t("chat:thinkingBadgeElapsedSec", { sec: elapsedSec });

  return (
    <Link
      to={href}
      className="ml-1 inline-flex max-w-[min(100%,18rem)] items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-medium text-amber-100/95 hover:bg-amber-500/20"
      title={label}
    >
      <span
        className="relative flex h-1.5 w-1.5 shrink-0"
        aria-hidden
      >
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70 opacity-75" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-300" />
      </span>
      <span className="min-w-0 truncate">{label}</span>
      <span className="shrink-0 tabular-nums text-amber-200/70">{timeLabel}</span>
    </Link>
  );
}
