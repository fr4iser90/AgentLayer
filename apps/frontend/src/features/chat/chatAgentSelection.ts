/**
 * Which agents the chat surface may select directly.
 *
 * Most specialists (coding, security_auditor, …) are delegate-only: the General agent
 * hands work to them, and the server rewrites any other ``agent_id`` to ``general``. An
 * agent that runs in an **external runtime** (agent.yaml ``external_runtime:``) is meant
 * to be driven by a person in the chat, so it is reachable via ``?agent=<id>``.
 *
 * The server still decides access (``min_role`` / tenant policy) — this list only decides
 * whether the deep link is honoured instead of falling back to General.
 */

export const DEEP_LINK_AGENT_IDS: ReadonlySet<string> = new Set(["knowledge_companion", "coding_qwen"]);

export function resolveComposerAgentId(opts: {
  dashboardChatId?: string | null;
  agentParam?: string | null;
}): string {
  if (opts.dashboardChatId) return "dashboard";
  const agent = (opts.agentParam ?? "").trim().toLowerCase();
  return DEEP_LINK_AGENT_IDS.has(agent) ? agent : "general";
}
