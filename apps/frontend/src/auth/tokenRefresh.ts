/** JWT access-token expiry (ms since epoch). No signature verify — schedule refresh only. */
export function jwtExpMs(token: string): number | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(b64)) as { exp?: unknown };
    const exp = payload.exp;
    return typeof exp === "number" && Number.isFinite(exp) ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Refresh this many ms before JWT exp so API calls never hit 401 from stale Bearer. */
export const ACCESS_REFRESH_BUFFER_MS = 2 * 60 * 1000;

export function accessTokenNeedsRefresh(token: string | null, now = Date.now()): boolean {
  if (!token) return false;
  const exp = jwtExpMs(token);
  if (exp == null) return false;
  return exp - now <= ACCESS_REFRESH_BUFFER_MS;
}

export function msUntilProactiveRefresh(token: string, now = Date.now()): number | null {
  const exp = jwtExpMs(token);
  if (exp == null) return null;
  return Math.max(0, exp - now - ACCESS_REFRESH_BUFFER_MS);
}
