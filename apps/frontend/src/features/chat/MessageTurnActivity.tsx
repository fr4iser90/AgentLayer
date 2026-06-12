import { useTranslation } from "react-i18next";
import type { AgentTimelineEntry } from "./chatThreadStorage";
import { buildRunCardsFromTimeline } from "./buildRunCards";
import { formatToolStepLabel } from "./toolStepLabel";

type Props = {
  entries: AgentTimelineEntry[];
  running?: boolean;
  waitHint?: string | null;
};

function isStepKind(kind: string): boolean {
  return (
    kind === "llm" ||
    kind === "session" ||
    kind === "tool_start" ||
    kind === "tool_done" ||
    kind === "subagent_start" ||
    kind === "subagent_step" ||
    kind === "subagent_done" ||
    kind === "wait" ||
    kind === "llm_queue" ||
    kind === "deferred_wait" ||
    kind === "scan_queue"
  );
}

/** LLM/tool/subagent steps in the assistant bubble (not context tokens — those stay in SessionRuntimeBar). */
export function MessageTurnActivity({ entries, running = false, waitHint = null }: Props) {
  const { t } = useTranslation(["chat"]);
  const cards = buildRunCardsFromTimeline(entries);
  const anchored = new Set(cards.flatMap((c) => c.details.map((d) => d.id)));

  const steps = entries.filter((e) => isStepKind(e.kind) && !anchored.has(e.id));

  if (steps.length === 0 && !running) return null;

  return (
    <div className="mb-2 rounded-lg border border-white/8 bg-black/25 px-2.5 py-2">
      <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wide text-surface-muted">
        {t("chat:messageRuntimeLabel")}
      </p>
      {steps.length === 0 ? (
        <p className="flex items-center gap-1.5 text-[11px] text-violet-200/85">
          <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
          {waitHint?.trim() || t("chat:agentRunning")}
        </p>
      ) : (
        <ul className="space-y-1">
          {steps.map((e) => (
            <li
              key={e.id}
              className="border-l-2 border-violet-500/40 pl-2 text-[11px] leading-snug text-neutral-300"
            >
              <span className="text-[9px] font-medium uppercase tracking-wide text-surface-muted">
                {e.kind === "llm"
                  ? t("chat:activityKindLlm")
                  : e.kind === "llm_queue"
                    ? t("chat:activityKindLlmQueue")
                    : e.kind === "deferred_wait" || e.kind === "scan_queue"
                      ? t("chat:activityKindDeferredWait")
                    : e.kind === "session"
                    ? t("chat:activityKindSession")
                    : e.kind.startsWith("subagent")
                      ? t("chat:activityKindSub")
                      : e.kind === "tool_done"
                        ? t("chat:activityKindDone")
                        : t("chat:activityKindTool")}
              </span>{" "}
              {e.kind === "tool_start" || e.kind === "tool_done"
                ? formatToolStepLabel(
                    e.toolName ?? "",
                    e.toolSummary,
                    undefined,
                    e.text
                  ) || e.text
                : e.text}
              {e.durationMs != null && e.durationMs >= 0 ? (
                <span className="ml-1 tabular-nums text-neutral-500">
                  {e.durationMs < 1000
                    ? `${e.durationMs}ms`
                    : `${(e.durationMs / 1000).toFixed(1)}s`}
                </span>
              ) : null}
            </li>
          ))}
          {running ? (
            <li className="flex items-center gap-1.5 border-l-2 border-violet-500/30 pl-2 text-[11px] text-violet-200/80">
              <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
              {waitHint?.trim() || t("chat:running")}
            </li>
          ) : null}
        </ul>
      )}
    </div>
  );
}
