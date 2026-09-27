import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";
import { defaultLandingPath } from "./tenantSurface";
import { holdsCapability, isSiteAdmin, type AdminCapability } from "../pages/admin/accessGating";

/**
 * One admin capability as a route guard.
 *
 * The whole admin area hangs off `RequireSiteAdmin`, so a delegated holder —
 * someone the API does let into a scope-gated endpoint — had no way to reach
 * the screen for it. `/admin/run-traces` is the clearest case: all three of its
 * endpoints ask `require_admin_scope(request, "observability.read")` while the
 * route still demanded the platform operator. This guard is how a leaf moves
 * from "admin only" to "whatever the endpoint actually asks".
 *
 * It admits a site admin **or** the slug holder. The site-admin half is not
 * redundant: `isSiteAdmin` also reads the legacy `role === "admin"` payload,
 * which every route below `RequireSiteAdmin` has always accepted, so asking the
 * slug alone would take pages away from accounts the API still serves. The
 * capability half has no such fallback — `require_admin_scope` never had one,
 * see `holdsCapability`.
 *
 * A UI reduction, not a security boundary: the API keeps enforcing the slug and
 * the tenant scope no matter what renders here.
 */
export function RequireCapability({
  cap,
  children
}: {
  cap: AdminCapability;
  children: ReactNode;
}) {
  const { t } = useTranslation(["auth"]);
  const { accessToken, user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-wide text-sm text-ink-muted">
        {t("auth:loading")}
      </div>
    );
  }

  if (!accessToken) {
    window.location.replace("/app/login");
    return null;
  }

  if (isSiteAdmin(user) || holdsCapability(user, cap)) {
    return <>{children}</>;
  }

  return <Navigate to={defaultLandingPath(user)} replace />;
}