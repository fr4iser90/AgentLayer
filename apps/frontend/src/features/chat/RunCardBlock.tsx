import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { RunCard } from "./buildRunCards";

type Props = {
  card: RunCard;
  defaultExpanded?: boolean;
};

function borderForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "border-indigo-500/45";
  if (kind === "index") return "border-violet-500/45";
  return "border-sky-500/35";
}

function bgForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "bg-indigo-950/25";
  if (kind === "index") return "bg-violet-950/20";
  return "bg-sky-950/15";
}

function iconForKind(kind: RunCard["kind"]): string {
  if (kind === "subagent") return "🤖";
  if (kind === "index") return "📇";
  return "🔧";
}

function formatDuration(ms: number | undefined, runningLabel: string): string | null {
  if (ms == null || ms < 0) return null;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

export function RunCardBlock({ card, defaultExpanded = false }: Props) {
  const { t } = useTranslation(["chat"]);
  const [expanded, setExpanded] = useState(defaultExpanded && card.status === "running");

  const title =
    card.kind === "subagent" && card.agentId
      ? t(`chat:runCardAgent_${card.agentId}`, { defaultValue: card.title })
      : card.kind === "index" && card.indexMode
        ? t(`chat:runCardIndex_${card.indexMode}`, { defaultValue: card.title })
        : card.title;

  const duration = formatDuration(card.durationMs, t("chat:running"));
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
  } else if (card.indexPhase) {
    meta.push(card.indexPhase);
  } else if (card.stepCount != null && card.stepCount > 0) {
    meta.push(t("chat:runCardStepCount", { count: card.stepCount }));
  }

  const showRecentInDetails =
    card.recentSteps && card.recentSteps.length > 0 && card.status !== "running";

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
          {card.status === "running" && card.currentStep ? (
            <p className="mt-1 truncate text-[11px] leading-snug text-sky-300/90">{card.currentStep}</p>
          ) : null}
          {card.details.length > 0 || showRecentInDetails ? (
            <button
              type="button"
              className="mt-1.5 text-[10px] text-sky-400/90 hover:text-sky-300 hover:underline"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? t("chat:runCardHideDetails") : t("chat:runCardShowDetails")}
            </button>
          ) : null}
          {expanded ? (
            <ul className="mt-2 space-y-1 border-t border-white/5 pt-2">
              {showRecentInDetails
                ? card.recentSteps!.map((step, i) => (
                    <li key={`step-${i}`} className="text-[10px] leading-snug text-neutral-500">
                      <span className="text-emerald-400/70">✓</span>
                      <span className="text-neutral-400"> {step}</span>
                    </li>
                  ))
                : null}
              {card.details.map((d) => (
                <li key={d.id} className="text-[10px] leading-snug text-neutral-500">
                  <span className="font-medium uppercase tracking-wide text-surface-muted">
                    {d.kind}
                  </span>
                  {d.toolName ? <span className="text-indigo-300/80"> {d.toolName}</span> : null}
                  {d.text && d.kind !== "subagent_step" ? (
                    <span className="text-neutral-400"> — {d.text}</span>
                  ) : null}
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
          <RunCardBlock key={c.id} card={c} defaultExpanded={c.status === "running"} />
        ))}
      </div>
    </li>
  );
}
