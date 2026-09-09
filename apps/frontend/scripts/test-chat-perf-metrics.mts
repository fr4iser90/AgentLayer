/**
 * Smoke checks for chatPerfMetrics sample ring + turn marks.
 * Run: ``node --experimental-strip-types apps/frontend/scripts/test-chat-perf-metrics.mts``
 * (Node 22+) or skip if strip-types unavailable — logic is also exercised manually via
 * ``window.__agentlayerChatPerf``.
 */
import {
  chatPerfBeginTurn,
  chatPerfClear,
  chatPerfDump,
  chatPerfEndTurn,
  chatPerfNoteFirstDelta,
  chatPerfRecord,
  chatPerfSummary,
} from "../src/features/chat/chatPerfMetrics.ts";

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

chatPerfClear();
chatPerfRecord("conversations_list", 12.3, { phase: "test" });
chatPerfRecord("conversation_detail", 45, { phase: "test" });
chatPerfBeginTurn("t1", "u1");
chatPerfNoteFirstDelta("t1", "u1");
chatPerfNoteFirstDelta("t1", "u1"); // no-op second
chatPerfEndTurn("t1", "u1");

const dump = chatPerfDump();
assert(dump.length === 4, `expected 4 samples, got ${dump.length}`);
assert(dump.some((s) => s.kind === "send_to_first_delta"), "missing ttfd");
assert(dump.some((s) => s.kind === "turn_latency"), "missing turn_latency");

const summary = chatPerfSummary();
assert(summary.conversations_list?.n === 1, "list summary");
assert(summary.send_to_first_delta?.n === 1, "ttfd summary");

chatPerfClear();
assert(chatPerfDump().length === 0, "clear failed");
console.log("ok chat-perf-metrics");
