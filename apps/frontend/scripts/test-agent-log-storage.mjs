/** Round-trip checks for agent timeline persistence helpers (mirrors agentLogStorage.ts). */

function appendTimelineEntry(log, entry) {
  return [
    ...log,
    {
      id: entry.id ?? `${Date.now()}-${log.length}`,
      kind: entry.kind,
      text: entry.text,
      ...(entry.toolName != null ? { toolName: entry.toolName } : {}),
      ...(entry.subagentAgentId != null ? { subagentAgentId: entry.subagentAgentId } : {}),
      ...(entry.subagentRunId != null ? { subagentRunId: entry.subagentRunId } : {}),
      ...(entry.toolSummary != null ? { toolSummary: entry.toolSummary } : {}),
      ...(entry.stepPhase != null ? { stepPhase: entry.stepPhase } : {}),
      ...(entry.toolRound != null ? { toolRound: entry.toolRound } : {}),
    },
  ];
}

function agentLogPayloadEntryCount(agentLog, turnLogs) {
  const current = agentLog?.length ?? 0;
  const archived = (turnLogs ?? []).reduce((n, t) => n + (t.entries?.length ?? 0), 0);
  return current + archived;
}

function mergeAgentLogPreferRicher(server, local) {
  const serverN = agentLogPayloadEntryCount(server.agentLog, server.turnLogs);
  const localN = agentLogPayloadEntryCount(local.agentLog, local.turnLogs);
  if (localN > serverN) {
    return { agentLog: local.agentLog ?? [], turnLogs: local.turnLogs ?? [] };
  }
  return { agentLog: server.agentLog ?? [], turnLogs: server.turnLogs ?? [] };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const log = appendTimelineEntry([], {
  kind: "subagent_step",
  text: "Reading friends_db.py",
  subagentAgentId: "coding",
  subagentRunId: "run-a",
  stepPhase: "start",
  toolName: "read_file",
  toolSummary: "path=friends_db.py",
  toolRound: 2,
});

assert(log.length === 1, "one entry");
const e = log[0];
assert(e.subagentRunId === "run-a", "subagentRunId preserved");
assert(e.stepPhase === "start", "stepPhase preserved");
assert(e.toolSummary === "path=friends_db.py", "toolSummary preserved");
assert(e.toolRound === 2, "toolRound preserved");

const merged = mergeAgentLogPreferRicher(
  { agentLog: [], turnLogs: [] },
  {
    agentLog: [{ id: "1", kind: "subagent_start", text: "x" }],
    turnLogs: [{ userMessageId: "u1", entries: [{ id: "2", kind: "subagent_done", text: "done" }] }],
  }
);
assert(merged.agentLog.length === 1, "prefer local current");
assert(merged.turnLogs.length === 1, "prefer local turns");

console.log("test-agent-log-storage: ok");
