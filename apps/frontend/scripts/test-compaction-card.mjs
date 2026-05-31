/** Compaction run card from timeline (mirrors buildRunCards.ts). */
import assert from "node:assert/strict";

function buildRunCardsFromTimeline(entries) {
  const cards = [];
  for (const e of entries) {
    if (e.kind === "compaction_done") {
      cards.push({
        id: e.id,
        kind: "compaction",
        status: "done",
        title: e.compactionPhase === "history" ? "Chat history compacted" : "Tool context compacted",
        subtitle: e.text?.trim() || undefined,
        compactionPhase: e.compactionPhase,
        providerPromptTokens: e.providerPromptTokens,
        toolRoundsDropped: e.toolRoundsDropped,
      });
    }
  }
  return cards;
}

const loop = buildRunCardsFromTimeline([
  {
    id: "1",
    kind: "compaction_done",
    text: "95,432 / 76,800 soft tok · 3 tool rounds → summary",
    compactionPhase: "loop",
    providerPromptTokens: 95432,
    softLimitTokens: 76800,
    toolRoundsDropped: 3,
  },
]);

assert.equal(loop.length, 1);
assert.equal(loop[0].kind, "compaction");
assert.equal(loop[0].compactionPhase, "loop");
assert.equal(loop[0].toolRoundsDropped, 3);

console.log("test-compaction-card.mjs OK");
