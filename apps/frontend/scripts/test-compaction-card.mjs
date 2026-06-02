/** Compaction timeline + run card display (mirrors compactionActivity + RunCardBlock rules). */
import assert from "node:assert/strict";

function resolveMessagesCompacted(msg) {
  if (msg.messages_compacted_this_run > 0) return msg.messages_compacted_this_run;
  if (msg.messages_dropped > 0) return msg.messages_dropped;
  if (msg.summary_covers_messages > 0) return msg.summary_covers_messages;
  return undefined;
}

function compactionEventToTimeline(msg) {
  const phase = msg.phase === "history" ? "history" : "loop";
  const prompt = msg.provider_prompt_tokens;
  const soft = msg.soft_limit_tokens;
  const messagesCompacted = phase === "history" ? resolveMessagesCompacted(msg) : undefined;
  return {
    compactionPhase: phase,
    providerPromptTokens: phase === "loop" && prompt > 0 ? prompt : undefined,
    softLimitTokens: phase === "loop" ? soft : undefined,
    messagesCompacted,
    toolRoundsDropped: msg.tool_rounds_dropped,
  };
}

function runCardHeaderMeta(card) {
  if (card.compactionPhase === "loop") {
    const prompt = card.providerPromptTokens ?? 0;
    if (prompt > 0 && card.softLimitTokens != null) {
      return `${prompt.toLocaleString()} / ${card.softLimitTokens.toLocaleString()} tok`;
    }
    return "";
  }
  return "";
}

const history = compactionEventToTimeline({
  phase: "history",
  context_window_tokens: 262144,
  messages_compacted_this_run: 36,
  budget_source: "provider_catalog",
});
assert.equal(history.compactionPhase, "history");
assert.equal(history.messagesCompacted, 36);
assert.equal(history.providerPromptTokens, undefined);
assert.equal(runCardHeaderMeta(history), "");

const loop = compactionEventToTimeline({
  phase: "loop",
  provider_prompt_tokens: 180000,
  soft_limit_tokens: 157286,
  tool_rounds_dropped: 3,
});
assert.equal(loop.compactionPhase, "loop");
assert.equal(loop.providerPromptTokens, 180000);
assert.equal(loop.toolRoundsDropped, 3);
assert.equal(runCardHeaderMeta(loop), "180,000 / 157,286 tok");

const historyNoTokens = compactionEventToTimeline({
  phase: "history",
  provider_prompt_tokens: 0,
  soft_limit_tokens: 157286,
  messages_dropped: 48,
});
assert.equal(historyNoTokens.providerPromptTokens, undefined);
assert.equal(historyNoTokens.messagesCompacted, 48);

console.log("test-compaction-card.mjs OK");
