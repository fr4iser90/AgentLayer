import type { AgentTimelineEntry } from "./chatThreadStorage";

export type SubagentActivityExtras = Pick<
  AgentTimelineEntry,
  "toolName" | "durationMs" | "resultChars" | "subagentAgentId" | "nested"
>;

/** Handle ``agent.subagent_start`` / ``agent.subagent_done`` WebSocket events. Returns true if handled. */
export function handleSubagentWsEvent(
  typ: string,
  msg: Record<string, unknown>,
  append: (kind: string, text: string, extras?: SubagentActivityExtras) => void,
  subagentStartTimes: Map<string, number>
): boolean {
  if (typ === "agent.subagent_start") {
    const sid = String(msg.subagent_run_id ?? "").trim() || "subagent";
    const aid = String(msg.agent_id ?? "subagent").trim();
    const detail = String(msg.detail ?? "Starting delegated run…").trim();
    subagentStartTimes.set(sid, Date.now());
    append("subagent_start", detail, {
      subagentAgentId: aid,
      nested: true,
      toolName: typeof msg.tool_name === "string" ? msg.tool_name : "coding_task",
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
      nested: true,
      durationMs,
      resultChars: ch && ch > 0 ? ch : undefined,
      toolName: typeof msg.tool_name === "string" ? msg.tool_name : "coding_task",
    });
    return true;
  }
  return false;
}
