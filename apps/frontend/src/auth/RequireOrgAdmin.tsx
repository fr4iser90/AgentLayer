import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";
import { hasOrgSurface } from "./deploymentMode";
import { defaultLandingPath } from "./tenantSurface";
import { canManageWorkspaceGrants } from "../pages/admin/accessGating";

/** Tenant org surface — `/app/org` (multi_tenant only). */
export function RequireOrgAdmin() {
  const { t } = useTranslation(["auth"]);
  const { accessToken, user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-4 text-sm text-surface-muted">
        {t("auth:loading")}
      </div>
    );
  }

  if (!accessToken) {
    window.location.replace("/app/login");
    return null;
  }

  if (!hasOrgSurface(user)) {
    return <Navigate to={defaultLandingPath(user)} replace />;
  }

  const tenantAdmin =
    user?.membership_role === "tenant_owner" || user?.membership_role === "tenant_admin";
  const canEditContent = user?.profession_policy?.can_edit_content === true;
  const canManageTeam = tenantAdmin || user?.profession_policy?.can_manage_profession === true;

  const onSetup = location.pathname.includes("/org/setup");
  const onKnowledge = location.pathname.includes("/org/knowledge");
  const onTeam = location.pathname.includes("/org/team");
  const onGrants = location.pathname.includes("/org/grants");

  // Company sharing is delegated work: a tenant admin, or anyone granted
  // `workspace.manage`, reaches it without being a site admin. The API
  // applies the same capability plus a tenant range; this only decides
  // whether the screen is reachable at all.
  const canManageGrants = tenantAdmin || canManageWorkspaceGrants(user);

  if (onTeam && !canManageTeam) {
    return <Navigate to="/org/knowledge" replace />;
  }

  if (onGrants && !canManageGrants) {
    return <Navigate to="/org/knowledge" replace />;
  }

  const orgAllowed =
    tenantAdmin || canEditContent || canManageGrants || (onTeam && canManageTeam);
  if (!orgAllowed) {
    return <Navigate to={defaultLandingPath(user)} replace />;
  }

  if (user?.org_setup_required && !onSetup) {
    const allowedBeforeSetup = tenantAdmin || (onKnowledge && canEditContent);
    if (!allowedBeforeSetup) {
      return <Navigate to="/org/setup" replace state={{ from: location.pathname }} />;
    }
  }

  return <Outlet />;
}
