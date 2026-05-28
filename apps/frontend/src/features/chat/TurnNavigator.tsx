import type { UiMessage } from "./chatThreadStorage";
import { titleFromFirstMessage } from "./chatThreadStorage";
import { useTranslation } from "react-i18next";

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
      className={`flex flex-col gap-1 ${className}`}
      aria-label={t("chat:conversationPromptsAria")}
    >
      <span className="px-1 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
        {t("chat:prompts")}
      </span>
      <ul className="flex flex-col gap-0.5 lg:max-h-[min(60vh,28rem)] lg:overflow-y-auto">
        {userTurns.map((turn) => {
          const active = turn.id === activeId;
          return (
            <li key={turn.id}>
              <button
                type="button"
                onClick={() => onSelect(turn.id)}
                title={turn.label}
                className={`w-full rounded-lg border px-2 py-1.5 text-left text-[11px] leading-snug transition-colors ${
                  active
                    ? "border-sky-500/50 bg-sky-950/40 text-sky-100"
                    : "border-transparent text-neutral-400 hover:border-white/10 hover:bg-white/5 hover:text-neutral-200"
                }`}
              >
                <span className="mr-1.5 tabular-nums text-[10px] text-surface-muted">{turn.index}</span>
                <span className="line-clamp-2">{turn.label}</span>
              </button>
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
    <div className={`flex gap-1.5 overflow-x-auto pb-1 lg:hidden ${className}`}>
      {userTurns.map((turn) => {
        const active = turn.id === activeId;
        return (
          <button
            key={turn.id}
            type="button"
            onClick={() => onSelect(turn.id)}
            title={turn.label}
            className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
              active
                ? "border-sky-500/50 bg-sky-950/40 text-sky-100"
                : "border-white/10 text-neutral-400 hover:bg-white/5"
            }`}
          >
            <span className="mr-1 tabular-nums text-[10px] opacity-70">{turn.index}</span>
            <span className="max-w-[8rem] truncate">{turn.label}</span>
          </button>
        );
      })}
    </div>
  );
}
