/**
 * Pure access predicates: the P6 (Weg B) columns of the People admin list and
 * the platform-operator question every surface door asks.
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

/** Enough of `/auth/me` to decide platform-operator questions. */
export interface SiteAdminActor {
  site_role?: string | null;
  /** Legacy payload; `RequireSiteAdmin` has always read `role === "admin"` too. */
  role?: string | null;
}

/**
 * Platform operator.
 *
 * This read existed twice — in `RequireSiteAdmin` and in the avatar menu's
 * `siteAdmin` local — which is how a door and the room it opens drift apart:
 * the menu decides what to show, the guard decides what to serve, and nothing
 * checks that they agree. `RequireSiteAdmin` and the nav model now ask this one
 * function. The legacy `role` read trims as well as lowercases, matching
 * `canUseSchedules`; a padded payload from an old identity provider used to
 * bounce in the UI while the API accepted it.
 */
export function isSiteAdmin(actor?: SiteAdminActor | null): boolean {
  if (actor?.site_role === "site_admin") return true;
  return String(actor?.role ?? "").trim().toLowerCase() === "admin";
}

const AGENT_ASSIGN_CAP = "agent.assign";
const WORKSPACE_MANAGE_CAP = "workspace.manage";

/**
 * Whether the actor may manage company sharing grants on workspaces.
 *
 * Mirrors the backend gate: `require_admin_scope(request, "workspace.manage")`,
 * which is the capability plus a tenant range. A site admin holds every
 * capability; a delegated holder needs the slug granted. The tenant range is
 * not expressible client-side and is deliberately not guessed here — the API
 * enforces it, this only decides whether the screen is reachable.
 */
export function canManageWorkspaceGrants(actor?: AccessActor | null): boolean {
  if (actor?.site_role === "site_admin") return true;
  return normalizeCapabilities(actor).has(WORKSPACE_MANAGE_CAP);
}

/** Tenant membership that owns or administers the company. */
export function isTenantAdmin(actor?: { membership_role?: string | null } | null): boolean {
  return actor?.membership_role === "tenant_owner" || actor?.membership_role === "tenant_admin";
}

/** Enough of `/auth/me` to decide whether any `/org` screen is reachable. */
export interface OrgActor extends AccessActor {
  membership_role?: string | null;
  profession_policy?: { can_edit_content?: boolean } | null;
}

/**
 * Whether this user reaches the `/org` surface at all — the door question,
 * answered with the route guard's predicate instead of the narrower copy the
 * avatar menu kept.
 *
 * `RequireOrgAdmin` admits a tenant admin, a content editor and a delegated
 * grants holder. The menu only knew the tenant-admin half, so a knowledge
 * editor with a legitimate `/org/knowledge` screen had no link to it anywhere:
 * the area's leaves live in the org rail, which is only on screen once you are
 * already inside the area.
 *
 * `hasOrgSurface` is deliberately not folded in — that is a deployment-mode
 * question the caller asks beside this one, so the mode stays visible in the
 * model rather than hiding inside a role test.
 */
export function canReachOrgSurface(actor?: OrgActor | null): boolean {
  if (isTenantAdmin(actor)) return true;
  if (actor?.profession_policy?.can_edit_content === true) return true;
  return canManageWorkspaceGrants(actor);
}

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
 * Visible column span for the list: base count (14 with the Tenant column
 * hidden, else 15) minus the agents column this actor may not see.
 */
export function visibleColSpan(
  actor?: AccessActor | null,
  hideTenantColumn = false
): number {
  const base = hideTenantColumn ? 14 : 15;
  return base - (canAssignAgents(actor) ? 0 : 1);
}
