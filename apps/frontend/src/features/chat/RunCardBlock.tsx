import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { RunCard } from "./buildRunCards";

type Props = {
  card: RunCard;
  /** Controlled expand state (survives parent remounts when lifted to ChatPage). */
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  /** Flip expand/collapse without passing the next boolean (used with lifted state). */
  onToggleExpanded?: () => void;
  defaultExpanded?: boolean;
};

function borderForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "border-indigo-500/45";
  if (kind === "index") return "border-violet-500/45";
  if (kind === "compaction") return "border-amber-500/45";
  return "border-sky-500/35";
}

function bgForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "bg-indigo-950/25";
  if (kind === "index") return "bg-violet-950/20";
  if (kind === "compaction") return "bg-amber-950/20";
  return "bg-sky-950/15";
}

function iconForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "🤖";
  if (kind === "index") return "📇";
  if (kind === "compaction") return "📦";
  return "🔧";
}

const COLLAPSED_PREVIEW_RUNNING = 2;
const COLLAPSED_PREVIEW_DONE = 1;

function formatDuration(ms: number | undefined): string | null {
  if (ms == null || ms < 0) return null;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

/** Last 1–2 step labels shown while the card stays collapsed. */
function collapsedStepPreview(card: RunCard): string[] {
  const steps = allSubagentStepLabels(card);
  if (steps.length > 0) {
    const max = card.status === "running" ? COLLAPSED_PREVIEW_RUNNING : COLLAPSED_PREVIEW_DONE;
    return steps.slice(-max);
  }
  const cur = card.currentStep?.trim();
  return cur ? [cur] : [];
}

function allSubagentStepLabels(card: RunCard): string[] {
  return card.details
    .filter((d) => d.kind === "subagent_step")
    .map((d) => d.text.trim())
    .filter(Boolean);
}

export function RunCardBlock({
  card,
  expanded: expandedProp,
  onExpandedChange,
  onToggleExpanded,
  defaultExpanded = false,
}: Props) {
  const { t } = useTranslation(["chat"]);
  const [expandedLocal, setExpandedLocal] = useState(defaultExpanded);
  const expanded = expandedProp ?? expandedLocal;
  const setExpanded = (next: boolean | ((v: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(expanded) : next;
    if (onExpandedChange) onExpandedChange(value);
    else setExpandedLocal(value);
  };

  const title =
    card.kind === "compaction"
      ? card.compactionPhase === "history"
        ? t("chat:runCardCompactionHistory")
        : t("chat:runCardCompactionLoop")
      : card.kind === "subagent" && card.agentId
      ? t(`chat:runCardAgent_${card.agentId}`, { defaultValue: card.title })
      : card.kind === "index" && card.indexMode
        ? t(`chat:runCardIndex_${card.indexMode}`, { defaultValue: card.title })
        : card.title;

  const duration = formatDuration(card.durationMs);
  const previewSteps = !expanded ? collapsedStepPreview(card) : [];
  const statusLabel =
    card.status === "running"
      ? t("chat:runCardStatusRunning")
      : card.status === "failed"
        ? t("chat:runCardStatusFailed")
        : t("chat:runCardStatusDone");

  const meta: string[] = [statusLabel];
  if (duration) meta.push(duration);
  if (card.resultChars != null && card.resultChars > 0) {
    meta.push(t("chat:runCardResultChars", { count: card.resultChars }));
  }
  if (card.filesTotal != null && card.filesTotal > 0) {
    meta.push(
      t("chat:runCardFilesProgress", {
        done: card.filesDone ?? 0,
        total: card.filesTotal,
      })
    );
  } else if (card.kind === "compaction") {
    if (card.providerPromptTokens != null && card.softLimitTokens != null) {
      meta.push(
        t("chat:runCardCompactionTokens", {
          prompt: card.providerPromptTokens.toLocaleString(),
          soft: card.softLimitTokens.toLocaleString(),
        })
      );
    }
    if (card.toolRoundsDropped != null && card.toolRoundsDropped > 0) {
      meta.push(t("chat:runCardCompactionRounds", { count: card.toolRoundsDropped }));
    }
  } else if (card.indexPhase) {
    meta.push(card.indexPhase);
  } else if (card.stepCount != null && card.stepCount > 0) {
    meta.push(t("chat:runCardStepCount", { count: card.stepCount }));
  }

  const allSteps = card.kind === "subagent" ? allSubagentStepLabels(card) : [];
  const compactionDetailLines =
    card.kind === "compaction"
      ? [
          card.subtitle,
          card.contextWindowTokens
            ? t("chat:runCardCompactionWindow", {
                count: card.contextWindowTokens.toLocaleString(),
              })
            : null,
          card.budgetSource
            ? t("chat:runCardCompactionSource", { source: card.budgetSource })
            : null,
        ].filter((x): x is string => Boolean(x && x.trim()))
      : [];
  const expandableDetails =
    card.kind === "compaction"
      ? compactionDetailLines.length > 0
      : card.kind === "subagent"
        ? allSteps.length > 0
        : card.details.length > 0;

  return (
    <div
      className={`w-full max-w-[min(100%,42rem)] rounded-xl border ${borderForKind(card.kind)} ${bgForKind(card.kind)} px-3 py-2.5 text-sm shadow-sm`}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-base leading-none" aria-hidden>
          {iconForKind(card.kind)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-medium text-neutral-100">{title}</span>
            <span className="text-[10px] text-surface-muted">{meta.join(" · ")}</span>
            {card.status === "running" ? (
              <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
            ) : null}
          </div>
          {card.subtitle ? (
            <p className="mt-1 text-[11px] leading-snug text-neutral-400">{card.subtitle}</p>
          ) : null}
          {!expanded && previewSteps.length > 0 ? (
            <ul className="mt-1 space-y-0.5" aria-live="polite">
              {previewSteps.map((step, i) => {
                const isLatest = i === previewSteps.length - 1;
                const running = card.status === "running";
                return (
                  <li
                    key={`preview-${i}-${step}`}
                    className="flex min-w-0 items-baseline gap-1 truncate text-[11px] leading-snug"
                  >
                    {running ? (
                      isLatest ? (
                        <span className="shrink-0 text-sky-400/90">→</span>
                      ) : (
                        <span className="shrink-0 text-neutral-600">·</span>
                      )
                    ) : (
                      <span className="shrink-0 text-emerald-400/70">✓</span>
                    )}
                    <span
                      className={
                        running && isLatest
                          ? "truncate text-sky-300/90"
                          : "truncate text-neutral-500"
                      }
                    >
                      {step}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : null}
          {expandableDetails ? (
            <button
              type="button"
              className="mt-1.5 text-[10px] text-sky-400/90 hover:text-sky-300 hover:underline"
              onClick={() => {
                if (onToggleExpanded) onToggleExpanded();
                else setExpanded(!expanded);
              }}
            >
              {expanded ? t("chat:runCardHideDetails") : t("chat:runCardShowDetails")}
            </button>
          ) : null}
          {expanded ? (
            <ul className="mt-2 space-y-1 border-t border-white/5 pt-2">
              {card.kind === "compaction"
                ? compactionDetailLines.map((line, i) => (
                    <li key={`cmp-${i}`} className="text-[10px] leading-snug text-neutral-400">
                      {line}
                    </li>
                  ))
                : allSteps.length > 0
                ? allSteps.map((step, i) => (
                    <li key={`step-${i}`} className="text-[10px] leading-snug text-neutral-500">
                      {card.status !== "running" ? (
                        <span className="text-emerald-400/70">✓</span>
                      ) : (
                        <span className="text-sky-400/70">→</span>
                      )}
                      <span className="text-neutral-400"> {step}</span>
                    </li>
                  ))
                : card.details.map((d) => (
                    <li key={d.id} className="text-[10px] leading-snug text-neutral-500">
                      <span className="font-medium uppercase tracking-wide text-surface-muted">
                        {d.kind}
                      </span>
                      {d.toolName ? <span className="text-indigo-300/80"> {d.toolName}</span> : null}
                      {d.text ? <span className="text-neutral-400"> — {d.text}</span> : null}
                    </li>
                  ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  );
}

type RunCardsRowProps = {
  cards: RunCard[];
};

export function RunCardsRow({ cards }: RunCardsRowProps) {
  if (cards.length === 0) return null;
  return (
    <li className="flex w-full justify-center">
      <div className="flex w-full max-w-[min(100%,42rem)] flex-col gap-2">
        {cards.map((c) => (
          <RunCardBlock key={c.id} card={c} />
        ))}
      </div>
    </li>
  );
}
