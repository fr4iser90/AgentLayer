/**
 * Pure P6 (Weg B) access predicates for the People admin list.
 *
 * Decided from the granted platform/admin ``capabilities`` (cumulative JSONB on
 * ``users.capabilities``) plus the authoritative ``site_role``. Extracted from
 * ``AdminUsers`` so the gating logic can be unit-tested without rendering the
 * ~900-line page or mocking i18n/router. Kept free of React/i18n imports.
 */

/** Only the actor fields the gating decisions actually read. */
export interface AccessActor {
  site_role?: string | null;
  capabilities?: readonly string[] | null;
}

/** Only the target field the editability decision reads. */
export interface AccessTarget {
  site_role?: string | null;
}

const AGENT_ASSIGN_CAP = "agent.assign";

/** Lowercase + trim each granted capability slug; drop blanks and duplicates. */
export function normalizeCapabilities(
  actor?: AccessActor | null
): Set<string> {
  const set = new Set<string>();
  for (const raw of actor?.capabilities ?? []) {
    const slug = String(raw).trim().toLowerCase();
    if (slug) set.add(slug);
  }
  return set;
}

/**
 * Whether the actor may see/edit the agent-assign column.
 * A site admin holds every capability; a delegated holder only what was granted.
 */
export function canAssignAgents(actor?: AccessActor | null): boolean {
  if (actor?.site_role === "site_admin") return true;
  return normalizeCapabilities(actor).has(AGENT_ASSIGN_CAP);
}

/**
 * Whether the actor may edit the target row.
 * A site admin may edit everyone. A delegated holder may edit any non-site-admin
 * user but never a site admin (mirrors the backend PATCH boundary).
 */
export function isTargetEditable(
  actor?: AccessActor | null,
  target?: AccessTarget | null
): boolean {
  if (actor?.site_role === "site_admin") return true;
  return target?.site_role !== "site_admin";
}

/**
 * Visible column span for the list: base count (14 in agent_system mode, else 15
 * with the Tenant column) minus the agents column this actor may not see.
 */
export function visibleColSpan(
  actor?: AccessActor | null,
  isAgentSystem = false
): number {
  const base = isAgentSystem ? 14 : 15;
  return base - (canAssignAgents(actor) ? 0 : 1);
}
