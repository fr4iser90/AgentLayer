import type { TFunction } from "i18next";
import type { AgentTimelineEntry } from "./chatThreadStorage";
import { useTranslation } from "react-i18next";

type Props = {
  entries: AgentTimelineEntry[];
  loading?: boolean;
  loadingHint?: string | null;
  emptyHint?: string;
  className?: string;
  /** Taller scroll area when placed in the header grid beside model/MCP controls. */
  layout?: "compact" | "header";
  /** Show checkbox to toggle sub-agent rows (delegated specialist runs). */
  showSubagentToggle?: boolean;
  showSubagents?: boolean;
  onShowSubagentsChange?: (show: boolean) => void;
};

function borderForKind(kind: string): string {
  if (kind === "subagent_start") return "border-indigo-500/55";
  if (kind === "subagent_done") return "border-indigo-400/45";
  if (kind === "tool_start") return "border-sky-500/50";
  if (kind === "tool_done") return "border-emerald-500/50";
  if (kind === "llm" || kind === "think") return "border-violet-500/45";
  if (kind === "goal") return "border-amber-500/45";
  if (kind === "todos") return "border-teal-500/45";
  if (kind === "plan") return "border-sky-500/45";
  if (kind === "llm_queue") return "border-amber-500/45";
  if (kind === "deferred_wait" || kind === "scan_queue") return "border-orange-500/45";
  if (kind === "permission") return "border-amber-500/50";
  if (kind === "session") return "border-neutral-600";
  if (kind === "context_inject") return "border-amber-500/45";
  if (kind === "agent.done") return "border-emerald-600/40";
  return "border-line";
}

function labelForKind(kind: string, tr: TFunction<"chat">): string {
  if (kind === "subagent_start") return tr("chat:activityKindSub");
  if (kind === "subagent_done") return tr("chat:activityKindSubDone");
  if (kind === "tool_start") return tr("chat:activityKindTool");
  if (kind === "tool_done") return tr("chat:activityKindDone");
  if (kind === "think") return tr("chat:activityKindThink");
  if (kind === "llm") return tr("chat:activityKindLlm");
  if (kind === "goal") return tr("chat:activityKindGoal");
  if (kind === "todos") return tr("chat:activityKindTodos");
  if (kind === "plan") return tr("chat:activityKindPlan");
  if (kind === "llm_queue") return tr("chat:activityKindLlmQueue");
  if (kind === "deferred_wait" || kind === "scan_queue") return tr("chat:activityKindDeferredWait");
  if (kind === "permission") return tr("chat:activityKindPerm");
  if (kind === "session") return tr("chat:activityKindSession");
  if (kind === "context_inject") return tr("chat:activityKindContextInject");
  if (kind.startsWith("agent.")) return kind.replace("agent.", "");
  return kind;
}

export function AgentActivityPanel({
  entries,
  loading,
  loadingHint = null,
  emptyHint,
  className = "",
  layout = "compact",
  showSubagentToggle = false,
  showSubagents = true,
  onShowSubagentsChange,
}: Props) {
  const { t } = useTranslation(["chat"]);
  const scrollClass =
    layout === "header"
      ? "min-h-[7rem] max-h-[min(11rem,28vh)] overflow-y-auto overscroll-contain px-firm py-snug"
      : "min-h-0 max-h-32 overflow-y-auto overscroll-contain px-firm py-snug";

  const visible = (showSubagents ? entries : entries.filter(
        (e) =>
          e.kind !== "subagent_start" &&
          e.kind !== "subagent_done" &&
          e.kind !== "subagent_step"
      )).filter(
    (e) =>
      e.kind !== "context_inject" &&
      (e.kind !== "subagent_step" || e.stepPhase !== "done")
  );

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden rounded-card border border-line bg-black/30 ${className}`}
    >
      <div className="flex shrink-0 items-center justify-between gap-base border-b border-line-subtle px-firm py-snug">
        <span className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
          {t("chat:agentActivity")}
        </span>
        {showSubagentToggle ? (
          <label className="flex cursor-pointer items-center gap-snug text-meta text-ink-muted">
            <input
              type="checkbox"
              className="rounded-tile border-line bg-field text-indigo-500"
              checked={showSubagents}
              onChange={(e) => onShowSubagentsChange?.(e.target.checked)}
            />
            {t("chat:subagents")}
          </label>
        ) : null}
      </div>
      <div className={scrollClass}>
        {visible.length === 0 && !loading ? (
          <p className="text-meta leading-snug text-ink-muted">
            {emptyHint ?? t("chat:noActivityYet")}
          </p>
        ) : (
          <ul className="space-y-tight">
            {visible.map((e) => (
              <li
                key={e.id}
                className={[
                  "border-l-2 text-meta leading-snug",
                  borderForKind(e.kind),
                  e.nested ? "ml-soft pl-base" : "pl-base",
                ].join(" ")}
              >
                <div className="flex flex-wrap items-baseline gap-x-snug gap-y-0">
                  <span className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                    {labelForKind(e.kind, t)}
                  </span>
                  {e.subagentAgentId ? (
                    <span className="text-meta text-indigo-300/90">{e.subagentAgentId}</span>
                  ) : null}
                  <span className="text-ink-secondary">{e.text}</span>
                  {e.durationMs != null && e.durationMs >= 0 ? (
                    <span className="tabular-nums text-ink-muted">
                      {e.durationMs < 1000
                        ? `${e.durationMs}ms`
                        : `${(e.durationMs / 1000).toFixed(1)}s`}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
            {loading ? (
              <li className="flex items-center gap-snug border-l-2 border-violet-500/40 pl-base text-meta text-violet-200/80">
                <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-pill bg-violet-400" />
                {loadingHint?.trim() || t("chat:running")}
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </div>
  );
}
