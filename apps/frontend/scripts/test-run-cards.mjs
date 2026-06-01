/** @typedef {{ id: string; kind: string; text: string; toolName?: string; durationMs?: number; resultChars?: number; subagentAgentId?: string; subagentRunId?: string; stepPhase?: string; indexMode?: string; runStatus?: string; filesDone?: number; filesTotal?: number }} Entry */

/**
 * @param {Entry[]} entries
 */
export function buildRunCardsFromTimeline(entries) {
  const cards = [];
  const openTools = new Map();

  function findRunningSubagent(e) {
    if (e.subagentRunId) {
      const byId = [...cards].reverse().find(
        (c) => c.kind === "subagent" && c.status === "running" && c.subagentRunId === e.subagentRunId
      );
      if (byId) return byId;
    }
    return [...cards].reverse().find(
      (c) => c.kind === "subagent" && c.status === "running" && (!e.subagentAgentId || c.agentId === e.subagentAgentId)
    );
  }

  for (const e of entries) {
    if (e.kind === "subagent_start") {
      cards.push({
        id: e.id,
        kind: "subagent",
        status: "running",
        agentId: e.subagentAgentId,
        subagentRunId: e.subagentRunId,
        subtitle: e.text.trim() || undefined,
        details: [e],
      });
      continue;
    }
    if (e.kind === "subagent_step") {
      const card = findRunningSubagent(e);
      if (card) {
        if (e.stepPhase === "done" && e.toolOk === false) {
          card.details.push(e);
          const label = e.text.trim();
          if (label) {
            const rs = card.recentSteps ?? [];
            card.recentSteps = (rs.length ? [...rs.slice(0, -1), label] : [label]).slice(-8);
            card.subtitle = label;
          }
          card.status = "failed";
        } else if (e.stepPhase !== "done") {
          card.details.push(e);
          const label = e.text.trim();
          if (label) {
            card.currentStep = label;
            card.recentSteps = [...(card.recentSteps ?? []), label].slice(-8);
          }
          card.stepCount = (card.stepCount ?? 0) + 1;
        }
      }
      continue;
    }
    if (e.kind === "subagent_done") {
      const card = findRunningSubagent(e);
      if (card) {
        const toolFailed = card.details.some(
          (d) => d.kind === "subagent_step" && d.stepPhase === "done" && d.toolOk === false
        );
        card.status =
          e.text.toLowerCase().includes("failed") || toolFailed ? "failed" : "done";
        card.durationMs = e.durationMs;
        card.currentStep = undefined;
        card.details.push(e);
      }
      continue;
    }
    if (e.kind === "index_start") {
      cards.push({ id: e.id, kind: "index", status: "running", indexMode: e.indexMode, details: [e] });
      continue;
    }
    if (e.kind === "index_done") {
      const card = [...cards].reverse().find(
        (c) => c.kind === "index" && c.status === "running" && (!e.indexMode || c.indexMode === e.indexMode)
      );
      if (card) {
        card.status = e.runStatus === "failed" ? "failed" : "done";
        card.durationMs = e.durationMs;
        card.details.push(e);
      }
      continue;
    }
    if (e.kind === "tool_start" && e.toolName === "index") {
      const card = { id: e.id, kind: "index", status: "running", indexMode: "code", toolName: e.toolName, details: [e] };
      cards.push(card);
      openTools.set(e.toolName, card);
    }
    if (e.kind === "tool_done" && e.toolName && openTools.has(e.toolName)) {
      const card = openTools.get(e.toolName);
      card.status = "done";
      card.durationMs = e.durationMs;
      card.details.push(e);
      openTools.delete(e.toolName);
    }
  }
  return cards;
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const subagentRun = buildRunCardsFromTimeline([
  { id: "1", kind: "subagent_start", text: "HIGH Security Fixes", subagentAgentId: "coding", subagentRunId: "run-a" },
  { id: "2", kind: "subagent_step", text: "Reading friends_db.py", subagentAgentId: "coding", subagentRunId: "run-a", stepPhase: "start" },
  { id: "3", kind: "subagent_step", text: "Reading friends_db.py", subagentAgentId: "coding", subagentRunId: "run-a", stepPhase: "done" },
  { id: "4", kind: "subagent_step", text: "Editing agent_tasks_store.py", subagentAgentId: "coding", subagentRunId: "run-a", stepPhase: "start" },
  { id: "5", kind: "subagent_done", text: "finished (100 chars)", subagentAgentId: "coding", subagentRunId: "run-a", durationMs: 4500, resultChars: 100 },
]);
assert(subagentRun.length === 1, "one subagent card");
assert(subagentRun[0].status === "done", "subagent done");
assert(subagentRun[0].agentId === "coding", "agent id");
assert(subagentRun[0].subtitle === "HIGH Security Fixes", "task subtitle preserved");
assert(subagentRun[0].stepCount === 2, "two tool starts");
assert(subagentRun[0].recentSteps?.length === 2, "two step labels from starts");
assert(subagentRun[0].recentSteps?.[0]?.includes("friends_db"), "first step label");
assert(!subagentRun[0].currentStep, "no live step when done");
assert(
  subagentRun[0].details.every((d) => d.stepPhase !== "done"),
  "done phases omitted from card details"
);
assert(subagentRun[0].details.filter((d) => d.kind === "subagent_step").length === 2, "start steps only in details");

const failedPush = buildRunCardsFromTimeline([
  { id: "1", kind: "subagent_start", text: "push policy", subagentAgentId: "coding", subagentRunId: "run-b" },
  {
    id: "2",
    kind: "subagent_step",
    text: "Coding: Git push",
    subagentAgentId: "coding",
    subagentRunId: "run-b",
    stepPhase: "start",
    toolName: "git_push",
  },
  {
    id: "3",
    kind: "subagent_step",
    text: "Coding: Git push — permission denied",
    subagentAgentId: "coding",
    subagentRunId: "run-b",
    stepPhase: "done",
    toolName: "git_push",
    toolOk: false,
    toolError: "permission denied",
  },
  { id: "4", kind: "subagent_done", text: "finished", subagentAgentId: "coding", subagentRunId: "run-b", durationMs: 1000 },
]);
assert(failedPush[0].status === "failed", "subagent card failed when a tool step failed");
assert(
  failedPush[0].recentSteps?.some((s) => s.includes("permission denied")),
  "failed tool error visible in recent steps"
);

const indexRun = buildRunCardsFromTimeline([
  { id: "a", kind: "index_start", text: "Docs index", indexMode: "docs" },
  { id: "b", kind: "index_done", text: "Docs index", indexMode: "docs", runStatus: "done", durationMs: 12000, filesDone: 40, filesTotal: 40 },
]);
assert(indexRun.length === 1, "one index card");
assert(indexRun[0].status === "done", "index done");
assert(indexRun[0].indexMode === "docs", "docs mode");

console.log("test-run-cards: ok");
