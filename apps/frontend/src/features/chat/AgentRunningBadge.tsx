import { useEffect, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getAgentChatSession } from "./agentChatSession";
import { useAgentWaitHint } from "./useAgentLiveTurn";
import { badgeClasses } from "../../ui/Badge";

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
      className={badgeClasses("accent", "ml-tight max-w-chipWide hover:bg-accent/25")}
      title={label}
    >
      <span
        className="relative flex h-1.5 w-1.5 shrink-0"
        aria-hidden
      >
        <span className="absolute inline-flex h-full w-full animate-ping rounded-pill bg-accent/70 opacity-75" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-pill bg-badge-accent" />
      </span>
      <span className="min-w-0 truncate">{label}</span>
      <span className="shrink-0 tabular-nums text-ink-muted">{timeLabel}</span>
    </Link>
  );
}
