import type { AuthContextValue } from "../auth/AuthContext";
import { apiFetch } from "./api";

export type GrantAccessLevel = "view" | "edit" | "manage";

/** The only minimum role a grant row needs to be written for.

`tenant_admin` and `tenant_owner` hold `manage` implicitly on a
tenant-visible entity (domain/access/entity_access.py), so a row naming them
changes nothing. `tenant_member` is the role that otherwise reaches nothing,
which makes it the only one worth editing. */
export const GRANT_MIN_ROLE_MEMBER = "tenant_member";

export type GrantRecord = {
  min_role: string;
  access: GrantAccessLevel;
  created_by?: string | null;
  created_at?: string | null;
};

export type EntityGrantsResponse = {
  entity_type: string;
  entity_id: string;
  tenant_id: number;
  grants: GrantRecord[];
};

type Auth = Pick<AuthContextValue, "accessToken" | "refresh">;

async function readError(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
  if (typeof body.detail === "string") return body.detail;
  return `${fallback} (${res.status})`;
}

export async function fetchEntityGrantsApi(
  auth: Auth,
  entityType: "workspace" | "dashboard",
  entityId: string
): Promise<EntityGrantsResponse> {
  const res = await apiFetch(
    `/v1/admin/entity-grants/${entityType}/${encodeURIComponent(entityId)}`,
    auth
  );
  if (!res.ok) {
    throw new Error(await readError(res, "Failed to load grants"));
  }
  return (await res.json()) as EntityGrantsResponse;
}

/** Sets the complete grant set for one entity. Anything omitted is revoked.

The endpoint replaces rather than patches, so callers must state the full
intent — including the empty list, which clears every grant. */
export async function replaceEntityGrantsApi(
  auth: Auth,
  entityType: "workspace" | "dashboard",
  entityId: string,
  grants: Array<{ min_role: string; access: GrantAccessLevel }>
): Promise<void> {
  const res = await apiFetch(
    `/v1/admin/entity-grants/${entityType}/${encodeURIComponent(entityId)}`,
    auth,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grants }),
    }
  );
  if (!res.ok) {
    throw new Error(await readError(res, "Failed to save grants"));
  }
}

/** The member access level implied by a grant set, or null when members get
nothing. Reads only the `tenant_member` row — the others are implicit. */
export function memberAccessLevel(
  grants: GrantRecord[] | undefined | null
): GrantAccessLevel | null {
  for (const g of grants ?? []) {
    if (String(g.min_role || "").toLowerCase() === GRANT_MIN_ROLE_MEMBER) {
      const access = String(g.access || "").toLowerCase();
      if (access === "view" || access === "edit" || access === "manage") return access;
    }
  }
  return null;
}

/** Builds the PUT payload for a chosen level. `null` means "no grant", which
is an empty set rather than a row with an empty access. */
export function grantsForLevel(level: GrantAccessLevel | null): Array<{
  min_role: string;
  access: GrantAccessLevel;
}> {
  return level === null ? [] : [{ min_role: GRANT_MIN_ROLE_MEMBER, access: level }];
}
