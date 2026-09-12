/**
 * Checks for the chat-surface agent selection (deep link → composer agent id).
 * Run: ``node --experimental-strip-types apps/frontend/scripts/test-chat-agent-selection.mts``
 * (Node 22+), or ``npm run test:chat-agent-selection`` from ``apps/frontend``.
 */
import {
  DEEP_LINK_AGENT_IDS,
  resolveComposerAgentId,
} from "../src/features/chat/chatAgentSelection.ts";
import { BUILD_AGENT_IDS } from "../src/features/chat/groupThreadsForSidebar.ts";

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

// External-runtime agents are meant to be driven from the chat, so ?agent= must stick.
assert(resolveComposerAgentId({ agentParam: "coding_qwen" }) === "coding_qwen", "?agent=coding_qwen honoured");

// Delegate-only specialists stay unreachable: the server rewrites them to general anyway.
for (const id of ["coding", "coding_plan", "security_auditor", "operator"]) {
  assert(resolveComposerAgentId({ agentParam: id }) === "general", `${id} is delegate-only`);
}

// Dashboard wins over the agent param; unknown, empty and cased params fall back.
assert(resolveComposerAgentId({ dashboardChatId: "d1", agentParam: "coding_qwen" }) === "dashboard", "dashboard wins");
assert(resolveComposerAgentId({ agentParam: "CODING_QWEN" }) === "coding_qwen", "case-insensitive param");
assert(resolveComposerAgentId({ agentParam: "  coding_qwen  " }) === "coding_qwen", "trimmed param");
assert(resolveComposerAgentId({ agentParam: "nope" }) === "general", "unknown agent falls back");
assert(resolveComposerAgentId({}) === "general", "no param defaults to general");
assert(resolveComposerAgentId({ agentParam: null }) === "general", "null param defaults to general");

// Whatever the composer can select for an external runtime must also be grouped under Build.
assert(DEEP_LINK_AGENT_IDS.has("coding_qwen"), "deep-link set names coding_qwen");
assert(BUILD_AGENT_IDS.has("coding_qwen"), "sidebar groups coding_qwen under Build");

console.log("ok chat-agent-selection");
