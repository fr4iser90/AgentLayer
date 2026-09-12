/**
 * Which agents the chat surface may select directly as the composer agent.
 *
 * Most specialists (coding, security_auditor, …) are delegate-only: the General
 * agent hands work to them, and the server rewrites any other ``agent_id`` to
 * ``general``. Two kinds of agent ARE directly composable:
 *  - an agent that runs in an **external runtime** (agent.yaml ``external_runtime:``)
 *    is meant to be driven by a person in the chat, so it is reachable via ``?agent=<id>``;
 *  - the ``knowledge_companion`` specialist.
 *
 * When the caller passes the filtered ``/v1/agents`` list (``invokableAgents``),
 * that list is authoritative: the deep link is honoured only for an agent the
 * caller may invoke. Otherwise the legacy ``DEEP_LINK_AGENT_IDS`` fallback applies.
 * The server always re-checks access before a turn runs, so this list only decides
 * whether a deep link is honoured instead of falling back to General.
 */

export const DEEP_LINK_AGENT_IDS: ReadonlySet<string> = new Set(["knowledge_companion", "coding_qwen"]);

export type DeepLinkableAgent = {
  id: string;
  /** Set when the agent runs outside AgentLayer's planner loop (e.g. ``qwen_code``). */
  external_runtime?: string | null;
};

/** Agents directly composable from the chat: the knowledge companion + external-runtime agents. */
function buildDirectlyComposableIds(agents: readonly DeepLinkableAgent[]): ReadonlySet<string> {
  const ids = new Set<string>();
  for (const a of agents) {
    const id = (a?.id ?? "").trim().toLowerCase();
    if (!id) continue;
    if (id === "knowledge_companion" || Boolean(a?.external_runtime)) {
      ids.add(id);
    }
  }
  return ids;
}

export function resolveComposerAgentId(opts: {
  dashboardChatId?: string | null;
  agentParam?: string | null;
  invokableAgents?: readonly DeepLinkableAgent[] | null;
}): string {
  if (opts.dashboardChatId) return "dashboard";
  const agent = (opts.agentParam ?? "").trim().toLowerCase();
  if (!agent) return "general";
  const composable = opts.invokableAgents
    ? buildDirectlyComposableIds(opts.invokableAgents)
    : DEEP_LINK_AGENT_IDS;
  return composable.has(agent) ? agent : "general";
}
