/**
 * Deployment-mode predicates for first-party chrome.
 *
 * Mirrors the backend readers (`operator_settings.has_org_surface` /
 * `is_single_user`) so the UI never re-derives the mode from a bare string
 * comparison. The bare form is the hazard: `=== "agent_system"` answers
 * "is this not single_user" for every mode added later, so a new mode inherits
 * whatever behaviour happened to be coded first rather than an explicit choice.
 *
 * Ask the question you actually mean — `hasOrgSurface`, `isSingleUser` — and a
 * fourth mode has to be classified here before it can render anything.
 */

import type { AuthUser } from "./AuthContext";

/** Mirrors ``DEPLOYMENT_MODES`` in ``apps/backend/domain/setup/instance.py``. */
export type DeploymentMode = "single_user" | "agent_system" | "multi_tenant";

const MODES: readonly DeploymentMode[] = ["single_user", "agent_system", "multi_tenant"];

/**
 * Narrow the wire value. An unknown or missing mode reads as `multi_tenant`,
 * the same fallback the backend reader applies — the widest surface, so a
 * misread mode never silently hides an admin's own controls.
 */
export function deploymentMode(user: AuthUser | null | undefined): DeploymentMode {
  const raw = String(user?.deployment_mode ?? "").trim().toLowerCase();
  for (const mode of MODES) {
    if (raw === mode) return mode;
  }
  return "multi_tenant";
}

/** Organizations product: the `/org` surface, tenant pickers, memberships. */
export function hasOrgSurface(user: AuthUser | null | undefined): boolean {
  return deploymentMode(user) === "multi_tenant";
}

/**
 * One person. Login is still required — this hides user management, tenant
 * selection and `/org`; it is not a security boundary.
 */
export function isSingleUser(user: AuthUser | null | undefined): boolean {
  return deploymentMode(user) === "single_user";
}
