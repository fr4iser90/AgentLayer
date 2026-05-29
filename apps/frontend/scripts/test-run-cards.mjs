/** @typedef {{ id: string; kind: string; text: string; toolName?: string; durationMs?: number; resultChars?: number; subagentAgentId?: string; indexMode?: string; runStatus?: string; filesDone?: number; filesTotal?: number }} Entry */

/**
 * @param {Entry[]} entries
 */
export function buildRunCardsFromTimeline(entries) {
  const cards = [];
  const openTools = new Map();

  for (const e of entries) {
    if (e.kind === "subagent_start") {
      cards.push({
        id: e.id,
        kind: "subagent",
        status: "running",
        agentId: e.subagentAgentId,
        details: [e],
      });
      continue;
    }
    if (e.kind === "subagent_done") {
      const card = [...cards].reverse().find(
        (c) => c.kind === "subagent" && c.status === "running" && (!e.subagentAgentId || c.agentId === e.subagentAgentId)
      );
      if (card) {
        card.status = e.text.toLowerCase().includes("failed") ? "failed" : "done";
        card.durationMs = e.durationMs;
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
    if (e.kind === "tool_start" && e.toolName === "coding_index") {
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
  { id: "1", kind: "subagent_start", text: "Starting", subagentAgentId: "coding" },
  { id: "2", kind: "subagent_done", text: "finished (100 chars)", subagentAgentId: "coding", durationMs: 4500, resultChars: 100 },
]);
assert(subagentRun.length === 1, "one subagent card");
assert(subagentRun[0].status === "done", "subagent done");
assert(subagentRun[0].agentId === "coding", "agent id");

const indexRun = buildRunCardsFromTimeline([
  { id: "a", kind: "index_start", text: "Docs index", indexMode: "docs" },
  { id: "b", kind: "index_done", text: "Docs index", indexMode: "docs", runStatus: "done", durationMs: 12000, filesDone: 40, filesTotal: 40 },
]);
assert(indexRun.length === 1, "one index card");
assert(indexRun[0].status === "done", "index done");
assert(indexRun[0].indexMode === "docs", "docs mode");

console.log("test-run-cards: ok");
