import type { UiMessage } from "./chatThreadStorage";
import { titleFromFirstMessage } from "./chatThreadStorage";
import { useTranslation } from "react-i18next";
import { Tooltip } from "../../ui/Tooltip";

export type TurnItem = { id: string; label: string; index: number };

type Props = {
  userTurns: TurnItem[];
  activeId: string | null;
  onSelect: (userMessageId: string) => void;
  className?: string;
};

export function buildTurnItems(
  messages: UiMessage[],
  labelMaxLen = 40,
  fallbackLabel?: (n: number) => string
): TurnItem[] {
  const items: TurnItem[] = [];
  let n = 0;
  for (const m of messages) {
    if (m.role !== "user" || !m.id) continue;
    n += 1;
    const label = titleFromFirstMessage(m.content, labelMaxLen);
    items.push({ id: m.id, label: label || (fallbackLabel ? fallbackLabel(n) : `Prompt ${n}`), index: n });
  }
  return items;
}

export function TurnNavigator({ userTurns, activeId, onSelect, className = "" }: Props) {
  const { t } = useTranslation(["chat"]);
  if (userTurns.length === 0) return null;

  return (
    <nav
      className={`flex flex-col gap-tight ${className}`}
      aria-label={t("chat:conversationPromptsAria")}
    >
      <span className="px-tight text-meta font-medium uppercase tracking-wide text-ink-muted">
        {t("chat:prompts")}
      </span>
      <ul className="flex flex-col gap-hair lg:max-h-[min(60vh,28rem)] lg:overflow-y-auto">
        {userTurns.map((turn) => {
          const active = turn.id === activeId;
          return (
            <li key={turn.id}>
              <Tooltip label={turn.label}>
              <button
                  type="button"
                  onClick={() => onSelect(turn.id)}
                  className={`w-full rounded-card border px-base py-snug text-left text-meta leading-snug transition-colors ${
                    active
                      ? "border-accent/50 bg-accent-subtle text-badge-accent"
                      : "border-transparent text-ink-muted hover:border-line hover:bg-white/5 hover:text-neutral-200"
                  }`}
                >
                  <span className="mr-snug tabular-nums text-meta text-ink-muted">{turn.index}</span>
                  <span className="line-clamp-2">{turn.label}</span>
                </button>
              </Tooltip>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Horizontal chips for narrow viewports. */
export function TurnNavigatorHorizontal({ userTurns, activeId, onSelect, className = "" }: Props) {
  const { t } = useTranslation(["chat"]);
  if (userTurns.length === 0) return null;
  return (
    <div className={`flex gap-snug overflow-x-auto pb-tight lg:hidden ${className}`}>
      {userTurns.map((turn) => {
        const active = turn.id === activeId;
        return (
          <Tooltip label={turn.label}>
          <button
              key={turn.id}
              type="button"
              onClick={() => onSelect(turn.id)}
              className={`shrink-0 rounded-pill border px-firm py-tight text-meta transition-colors ${
                active
                  ? "border-accent/50 bg-accent-subtle text-badge-accent"
                  : "border-line text-ink-muted hover:bg-white/5"
              }`}
            >
              <span className="mr-tight tabular-nums text-meta opacity-70">{turn.index}</span>
              <span className="max-w-chip truncate">{turn.label}</span>
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
