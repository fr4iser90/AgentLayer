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
  /** Show checkbox to toggle sub-agent rows (delegated coding_task runs). */
  showSubagentToggle?: boolean;
  showSubagents?: boolean;
  onShowSubagentsChange?: (show: boolean) => void;
};

function borderForKind(kind: string): string {
  if (kind === "subagent_start") return "border-indigo-500/55";
  if (kind === "subagent_done") return "border-indigo-400/45";
  if (kind === "tool_start") return "border-sky-500/50";
  if (kind === "tool_done") return "border-emerald-500/50";
  if (kind === "llm") return "border-violet-500/45";
  if (kind === "llm_queue") return "border-amber-500/45";
  if (kind === "deferred_wait" || kind === "scan_queue") return "border-orange-500/45";
  if (kind === "permission") return "border-amber-500/50";
  if (kind === "session") return "border-neutral-600";
  if (kind === "agent.done") return "border-emerald-600/40";
  return "border-surface-border";
}

function labelForKind(kind: string, tr: TFunction<"chat">): string {
  if (kind === "subagent_start") return tr("chat:activityKindSub");
  if (kind === "subagent_done") return tr("chat:activityKindSubDone");
  if (kind === "tool_start") return tr("chat:activityKindTool");
  if (kind === "tool_done") return tr("chat:activityKindDone");
  if (kind === "llm") return tr("chat:activityKindLlm");
  if (kind === "llm_queue") return tr("chat:activityKindLlmQueue");
  if (kind === "deferred_wait" || kind === "scan_queue") return tr("chat:activityKindDeferredWait");
  if (kind === "permission") return tr("chat:activityKindPerm");
  if (kind === "session") return tr("chat:activityKindSession");
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
      ? "min-h-[7rem] max-h-[min(11rem,28vh)] overflow-y-auto overscroll-contain px-2.5 py-1.5"
      : "min-h-0 max-h-32 overflow-y-auto overscroll-contain px-2.5 py-1.5";

  const visible = (showSubagents ? entries : entries.filter(
        (e) =>
          e.kind !== "subagent_start" &&
          e.kind !== "subagent_done" &&
          e.kind !== "subagent_step"
      )).filter(
    (e) => e.kind !== "subagent_step" || e.stepPhase !== "done"
  );

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-black/30 ${className}`}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/5 px-2.5 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-surface-muted">
          {t("chat:agentActivity")}
        </span>
        {showSubagentToggle ? (
          <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-surface-muted">
            <input
              type="checkbox"
              className="rounded border-surface-border bg-[#1a1a1a] text-indigo-500"
              checked={showSubagents}
              onChange={(e) => onShowSubagentsChange?.(e.target.checked)}
            />
            {t("chat:subagents")}
          </label>
        ) : null}
      </div>
      <div className={scrollClass}>
        {visible.length === 0 && !loading ? (
          <p className="text-[11px] leading-snug text-surface-muted">
            {emptyHint ?? t("chat:noActivityYet")}
          </p>
        ) : (
          <ul className="space-y-1">
            {visible.map((e) => (
              <li
                key={e.id}
                className={[
                  "border-l-2 text-[11px] leading-snug",
                  borderForKind(e.kind),
                  e.nested ? "ml-3 pl-2" : "pl-2",
                ].join(" ")}
              >
                <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0">
                  <span className="text-[9px] font-medium uppercase tracking-wide text-surface-muted">
                    {labelForKind(e.kind, t)}
                  </span>
                  {e.subagentAgentId ? (
                    <span className="text-[9px] text-indigo-300/90">{e.subagentAgentId}</span>
                  ) : null}
                  <span className="text-neutral-300">{e.text}</span>
                  {e.durationMs != null && e.durationMs >= 0 ? (
                    <span className="tabular-nums text-neutral-500">
                      {e.durationMs < 1000
                        ? `${e.durationMs}ms`
                        : `${(e.durationMs / 1000).toFixed(1)}s`}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
            {loading ? (
              <li className="flex items-center gap-1.5 border-l-2 border-violet-500/40 pl-2 text-[11px] text-violet-200/80">
                <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />
                {loadingHint?.trim() || t("chat:running")}
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </div>
  );
}
