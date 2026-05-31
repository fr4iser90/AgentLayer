import type { AgentTimelineEntry } from "./chatThreadStorage";
import { formatToolStepLabel } from "./toolStepLabel";

export type SubagentActivityExtras = Pick<
  AgentTimelineEntry,
  | "toolName"
  | "toolSummary"
  | "stepPhase"
  | "toolRound"
  | "durationMs"
  | "resultChars"
  | "subagentAgentId"
  | "subagentRunId"
  | "nested"
  | "streamOffset"
>;

/** Handle sub-agent WebSocket events. Returns true if handled. */
export function handleSubagentWsEvent(
  typ: string,
  msg: Record<string, unknown>,
  append: (kind: string, text: string, extras?: SubagentActivityExtras) => void,
  subagentStartTimes: Map<string, number>,
  streamOffset?: () => number
): boolean {
  if (typ === "agent.subagent_start") {
    const sid = String(msg.subagent_run_id ?? "").trim() || "subagent";
    const aid = String(msg.agent_id ?? "subagent").trim();
    const detail = String(msg.detail ?? "Starting delegated run…").trim();
    subagentStartTimes.set(sid, Date.now());
    append("subagent_start", detail, {
      subagentAgentId: aid,
      subagentRunId: sid,
      nested: true,
      toolName: typeof msg.tool_name === "string" ? msg.tool_name : "coding_task",
      streamOffset: streamOffset?.(),
    });
    return true;
  }
  if (typ === "agent.subagent_step") {
    const sid = String(msg.subagent_run_id ?? "").trim() || "subagent";
    const aid = String(msg.agent_id ?? "subagent").trim();
    const tool = typeof msg.tool === "string" ? msg.tool : undefined;
    const summary = typeof msg.summary === "string" ? msg.summary : undefined;
    const toolLabel = typeof msg.label === "string" ? msg.label.trim() : undefined;
    const stepLabel = typeof msg.step_label === "string" ? msg.step_label.trim() : undefined;
    const phase = msg.phase === "done" ? "done" : "start";
    const label = formatToolStepLabel(tool, summary, toolLabel, stepLabel);
    append("subagent_step", label, {
      subagentAgentId: aid,
      subagentRunId: sid,
      nested: true,
      toolName: tool,
      toolSummary: summary,
      stepPhase: phase,
      toolRound: msg.round != null ? Number(msg.round) : undefined,
    });
    return true;
  }
  if (typ === "agent.subagent_done") {
    const sid = String(msg.subagent_run_id ?? "").trim() || "subagent";
    const aid = String(msg.agent_id ?? "subagent").trim();
    const ok = msg.ok !== false;
    const detail = String(msg.detail ?? (ok ? "done" : "failed")).trim();
    let durationMs: number | undefined;
    const started = subagentStartTimes.get(sid);
    if (started != null) {
      durationMs = Date.now() - started;
      subagentStartTimes.delete(sid);
    }
    const ch = msg.result_chars != null ? Number(msg.result_chars) : undefined;
    append("subagent_done", ok ? detail : `failed: ${detail}`, {
      subagentAgentId: aid,
      subagentRunId: sid,
      nested: true,
      durationMs,
      resultChars: ch && ch > 0 ? ch : undefined,
      toolName: typeof msg.tool_name === "string" ? msg.tool_name : "coding_task",
    });
    return true;
  }
  return false;
}
