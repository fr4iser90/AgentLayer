import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, Check, FileText, Package, Wrench, X } from "lucide-react";
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

function iconForKind(kind: RunCard["kind"]): ReactNode {
  if (kind === "subagent") return <Bot className="h-4 w-4" />;
  if (kind === "index") return <FileText className="h-4 w-4" />;
  if (kind === "compaction") return <Package className="h-4 w-4" />;
  return <Wrench className="h-4 w-4" />;
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

type SubagentStepRow = { label: string; failed: boolean; resultDisplay?: string };

function allSubagentStepRows(card: RunCard): SubagentStepRow[] {
  const steps = card.details.filter((d) => d.kind === "subagent_step");
  const rows: SubagentStepRow[] = [];
  const usedDoneIds = new Set<string>();
  for (const d of steps) {
    if (d.stepPhase !== "start") continue;
    const label = d.text.trim();
    if (!label) continue;
    const tool = d.toolName;
    const failedDone = steps.find(
      (x) =>
        x.stepPhase === "done" &&
        x.toolOk === false &&
        tool &&
        x.toolName === tool &&
        !usedDoneIds.has(x.id)
    );
    if (failedDone) {
      usedDoneIds.add(failedDone.id);
      rows.push({
        label: failedDone.text.trim() || label,
        failed: true,
        resultDisplay: failedDone.resultDisplay?.trim() || undefined,
      });
      continue;
    }
    const done = steps.find(
      (x) =>
        x.stepPhase === "done" &&
        tool &&
        x.toolName === tool &&
        !usedDoneIds.has(x.id)
    );
    if (!done || done.toolOk !== false) {
      if (done) usedDoneIds.add(done.id);
      rows.push({
        label,
        failed: false,
        resultDisplay: done?.resultDisplay?.trim() || undefined,
      });
    }
  }
  for (const d of steps) {
    if (d.stepPhase !== "done" || d.toolOk !== false || usedDoneIds.has(d.id)) continue;
    const tool = d.toolName;
    const hasStart = steps.some(
      (x) => x.stepPhase === "start" && tool && x.toolName === tool
    );
    if (!hasStart) {
      const label = d.text.trim();
      if (label) {
        rows.push({
          label,
          failed: true,
          resultDisplay: d.resultDisplay?.trim() || undefined,
        });
      }
    }
  }
  return rows;
}

function allSubagentStepLabels(card: RunCard): string[] {
  return allSubagentStepRows(card).map((r) => r.label);
}

function compactionCardSubtitle(
  card: RunCard,
  t: ReturnType<typeof useTranslation<["chat"]>>["t"]
): string | undefined {
  if (card.compactionPhase === "history") {
    const parts: string[] = [t("chat:compactionHistorySubtitle")];
    if (card.messagesCompacted != null && card.messagesCompacted > 0) {
      parts.push(t("chat:runCardCompactionMessages", { count: card.messagesCompacted }));
    }
    if (card.contextWindowTokens != null && card.contextWindowTokens > 0) {
      parts.push(
        t("chat:runCardCompactionWindow", {
          count: card.contextWindowTokens.toLocaleString(),
        })
      );
    }
    if (card.budgetSource?.trim()) {
      parts.push(t("chat:runCardCompactionSource", { source: card.budgetSource.trim() }));
    }
    return parts.join(" · ");
  }
  const parts: string[] = [];
  if (card.toolRoundsDropped != null && card.toolRoundsDropped > 0) {
    parts.push(t("chat:runCardCompactionRounds", { count: card.toolRoundsDropped }));
  }
  if (card.toolRound != null && card.toolRound > 0) {
    parts.push(t("chat:compactionLoopAfterRound", { round: card.toolRound }));
  }
  if (parts.length > 0) return parts.join(" · ");
  return card.subtitle?.trim() || undefined;
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

  const compactionSubtitle =
    card.kind === "compaction" ? compactionCardSubtitle(card, t) : undefined;

  const duration = formatDuration(card.durationMs);
  const previewSteps = !expanded ? collapsedStepPreview(card) : [];
  const statusLabel =
    card.status === "running"
      ? t("chat:runCardStatusRunning")
      : card.status === "failed"
        ? t("chat:runCardStatusFailed")
        : card.status === "cancelled"
          ? t("chat:runCardStatusCancelled")
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
    if (card.compactionPhase === "loop") {
      const prompt = card.providerPromptTokens ?? 0;
      if (prompt > 0 && card.softLimitTokens != null) {
        meta.push(
          t("chat:runCardCompactionTokens", {
            prompt: prompt.toLocaleString(),
            soft: card.softLimitTokens.toLocaleString(),
          })
        );
      }
    }
  } else if (card.indexPhase) {
    meta.push(card.indexPhase);
  } else if (card.stepCount != null && card.stepCount > 0) {
    meta.push(t("chat:runCardStepCount", { count: card.stepCount }));
  }

  const allSteps = card.kind === "subagent" ? allSubagentStepLabels(card) : [];
  const stepRows = card.kind === "subagent" ? allSubagentStepRows(card) : [];
  const lastOutputRow = !expanded
    ? [...stepRows].reverse().find((r) => r.resultDisplay?.trim())
    : undefined;
  const toolCardOutput =
    !expanded && card.kind === "tool"
      ? card.details
          .slice()
          .reverse()
          .find((d) => d.kind === "tool_done" && d.resultDisplay?.trim())
          ?.resultDisplay?.trim()
      : undefined;
  const compactionDetailLines =
    card.kind === "compaction"
      ? [
          compactionSubtitle,
          card.compactionPhase === "loop" && card.contextWindowTokens
            ? t("chat:runCardCompactionWindow", {
                count: card.contextWindowTokens.toLocaleString(),
              })
            : null,
          card.compactionPhase === "loop" && card.budgetSource
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
      className={`w-full max-w-[min(100%,42rem)] rounded-sheet border ${borderForKind(card.kind)} ${bgForKind(card.kind)} px-3 py-2.5 text-sm shadow-sm`}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-base leading-none" aria-hidden>
          {iconForKind(card.kind)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-medium text-ink-primary">{title}</span>
            <span className="text-meta text-ink-muted">{meta.join(" · ")}</span>
            {card.status === "running" ? (
              <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-pill bg-violet-400" />
            ) : null}
          </div>
          {compactionSubtitle ?? card.subtitle ? (
            <p className="mt-1 text-meta leading-snug text-ink-muted">
              {compactionSubtitle ?? card.subtitle}
            </p>
          ) : null}
          {card.kind === "subagent" && card.subagentRunId ? (
            <p className="mt-1 text-meta">
              <Link
                to={`/admin/run-traces?run=${encodeURIComponent(card.subagentRunId)}`}
                className="font-mono text-sky-400/90 hover:text-sky-300 hover:underline"
                title={t("chat:runCardOpenTrace")}
              >
                {t("chat:runCardRunId", { id: card.subagentRunId.slice(0, 8) })}
              </Link>
            </p>
          ) : null}
          {card.kind === "subagent" &&
          (card.reasoningExcerpt?.trim() || card.assistantExcerpt?.trim()) ? (
            <div className="mt-2 space-y-1.5">
              {card.reasoningExcerpt?.trim() ? (
                <details className="group/r">
                  <summary className="cursor-pointer list-none text-meta font-medium text-sky-200/80 marker:content-none [&::-webkit-details-marker]:hidden">
                    {t("chat:runCardThinking", { defaultValue: "Thinking" })}
                    <span className="ml-1 font-normal text-sky-200/50 group-open/r:hidden">
                      {t("chat:contextInjectExpandHint")}
                    </span>
                  </summary>
                  <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-sky-500/20 bg-black/25 px-2 py-1.5 font-sans text-meta leading-relaxed text-ink-muted">
                    {card.reasoningExcerpt.trim()}
                  </pre>
                </details>
              ) : null}
              {card.assistantExcerpt?.trim() ? (
                <details className="group/a" open={card.status === "running"}>
                  <summary className="cursor-pointer list-none text-meta font-medium text-indigo-200/85 marker:content-none [&::-webkit-details-marker]:hidden">
                    {t("chat:runCardOutput", { defaultValue: "Output" })}
                    <span className="ml-1 font-normal text-indigo-200/50 group-open/a:hidden">
                      {t("chat:contextInjectExpandHint")}
                    </span>
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-indigo-500/20 bg-black/25 px-2 py-1.5 font-sans text-meta leading-relaxed text-ink-secondary">
                    {card.assistantExcerpt.trim()}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : null}
          {!expanded && previewSteps.length > 0 ? (
            <ul className="mt-1 space-y-0.5" aria-live="polite">
              {previewSteps.map((step, i) => {
                const isLatest = i === previewSteps.length - 1;
                const running = card.status === "running";
                const failed =
                  card.kind === "subagent" &&
                  stepRows[stepRows.length - previewSteps.length + i]?.failed === true;
                return (
                  <li
                    key={`preview-${i}-${step}`}
                    className="flex min-w-0 items-baseline gap-1 truncate text-meta leading-snug"
                  >
                    {running ? (
                      isLatest ? (
                        <span className="shrink-0 text-sky-400/90">→</span>
                      ) : (
                        <span className="shrink-0 text-ink-faint">·</span>
                      )
                    ) : failed ? (
                      <span className="shrink-0" title={t("chat:runCardStepFailed")}>
                        <X aria-hidden className="h-3.5 w-3.5 text-rose-400/90" />
                      </span>
                    ) : (
                      <Check aria-hidden className="h-3.5 w-3.5 shrink-0 text-emerald-400/70" />
                    )}
                    <span
                      className={
                        running && isLatest
                          ? "truncate text-sky-300/90"
                          : "truncate text-ink-muted"
                      }
                    >
                      {step}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : null}
          {!expanded && (lastOutputRow?.resultDisplay || toolCardOutput) ? (
            <details
              className="group/out mt-1.5"
              open={lastOutputRow?.failed === true || card.status === "failed"}
            >
              <summary className="cursor-pointer list-none text-meta font-medium text-emerald-200/80 marker:content-none [&::-webkit-details-marker]:hidden">
                {t("chat:runCardCommandOutput")}
                <span className="ml-1 font-normal text-emerald-200/45 group-open/out:hidden">
                  {t("chat:contextInjectExpandHint")}
                </span>
              </summary>
              <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-emerald-500/20 bg-black/30 px-2 py-1.5 font-mono text-meta leading-relaxed text-ink-secondary">
                {lastOutputRow?.resultDisplay || toolCardOutput}
              </pre>
            </details>
          ) : null}
          {expandableDetails ? (
            <button
              type="button"
              className="mt-1.5 text-meta text-sky-400/90 hover:text-sky-300 hover:underline"
              onClick={() => {
                if (onToggleExpanded) onToggleExpanded();
                else setExpanded(!expanded);
              }}
            >
              {expanded ? t("chat:runCardHideDetails") : t("chat:runCardShowDetails")}
            </button>
          ) : null}
          {expanded ? (
            <ul className="mt-2 space-y-1 border-t border-line-subtle pt-2">
              {card.kind === "compaction"
                ? compactionDetailLines.map((line, i) => (
                    <li key={`cmp-${i}`} className="text-meta leading-snug text-ink-muted">
                      {line}
                    </li>
                  ))
                : allSubagentStepRows(card).length > 0
                ? allSubagentStepRows(card).map((row, i) => (
                    <li key={`step-${i}`} className="text-meta leading-snug text-ink-muted">
                      <div>
                        {card.status === "running" ? (
                          <span className="text-sky-400/70">→</span>
                        ) : row.failed ? (
                          <span className="inline" title={t("chat:runCardStepFailed")}>
                            <X aria-hidden className="inline h-3.5 w-3.5 text-rose-400/90" />
                          </span>
                        ) : (
                          <Check aria-hidden className="inline h-3.5 w-3.5 text-emerald-400/70" />
                        )}
                        <span className={row.failed ? "text-rose-200/85" : "text-ink-muted"}>
                          {" "}
                          {row.label}
                        </span>
                      </div>
                      {row.resultDisplay ? (
                        <details className="group/out mt-1" open={row.failed}>
                          <summary className="cursor-pointer list-none text-meta font-medium text-emerald-200/80 marker:content-none [&::-webkit-details-marker]:hidden">
                            {t("chat:runCardCommandOutput")}
                            <span className="ml-1 font-normal text-emerald-200/45 group-open/out:hidden">
                              {t("chat:contextInjectExpandHint")}
                            </span>
                          </summary>
                          <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-emerald-500/20 bg-black/30 px-2 py-1.5 font-mono text-meta leading-relaxed text-ink-secondary">
                            {row.resultDisplay}
                          </pre>
                        </details>
                      ) : null}
                    </li>
                  ))
                : card.details.map((d) => (
                    <li key={d.id} className="text-meta leading-snug text-ink-muted">
                      <div>
                        <span className="font-medium uppercase tracking-wide text-ink-muted">
                          {d.kind}
                        </span>
                        {d.toolName ? <span className="text-indigo-300/80"> {d.toolName}</span> : null}
                        {d.text ? <span className="text-ink-muted"> — {d.text}</span> : null}
                      </div>
                      {d.resultDisplay?.trim() ? (
                        <details className="group/out mt-1" open={d.toolOk === false}>
                          <summary className="cursor-pointer list-none text-meta font-medium text-emerald-200/80 marker:content-none [&::-webkit-details-marker]:hidden">
                            {t("chat:runCardCommandOutput")}
                            <span className="ml-1 font-normal text-emerald-200/45 group-open/out:hidden">
                              {t("chat:contextInjectExpandHint")}
                            </span>
                          </summary>
                          <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-emerald-500/20 bg-black/30 px-2 py-1.5 font-mono text-meta leading-relaxed text-ink-secondary">
                            {d.resultDisplay.trim()}
                          </pre>
                        </details>
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
          <RunCardBlock key={c.id} card={c} />
        ))}
      </div>
    </li>
  );
}
