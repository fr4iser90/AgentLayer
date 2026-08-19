/** Generic first-party nav allowlist from ``/auth/me`` → ``allowed_nav``. */

import type { AuthUser } from "./AuthContext";

export type NavItemId =
  | "home"
  | "chat"
  | "studio"
  | "dashboard"
  | "schedules"
  | "tasks"
  | "shares";

/** When ``user.allowed_nav`` is set, chrome is limited to those ids. ``null`` = full app. */
export function allowedNavItems(user: AuthUser | null | undefined): NavItemId[] | null {
  const raw = user?.allowed_nav;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const out: NavItemId[] = [];
  for (const x of raw) {
    const id = String(x || "")
      .trim()
      .toLowerCase() as NavItemId;
    if (
      id === "home" ||
      id === "chat" ||
      id === "studio" ||
      id === "dashboard" ||
      id === "schedules" ||
      id === "tasks" ||
      id === "shares"
    ) {
      out.push(id);
    }
  }
  return out.length ? out : null;
}

export function navItemAllowed(user: AuthUser | null | undefined, item: NavItemId): boolean {
  const allowed = allowedNavItems(user);
  if (allowed === null) return true;
  return allowed.includes(item);
}

/** True when the tenant has a restricted nav allowlist (not the full consumer chrome). */
export function hasRestrictedNav(user: AuthUser | null | undefined): boolean {
  return allowedNavItems(user) !== null;
}

export function defaultLandingPath(user: AuthUser | null | undefined): string {
  const allowed = allowedNavItems(user);
  if (allowed === null) return "/";
  for (const id of ["dashboard", "home", "chat"] as const) {
    if (allowed.includes(id)) {
      return id === "home" ? "/" : `/${id}`;
    }
  }
  return "/";
}
