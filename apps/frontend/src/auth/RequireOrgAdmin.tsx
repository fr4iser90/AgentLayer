import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";

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

  if (user?.deployment_mode === "agent_system") {
    return <Navigate to="/" replace />;
  }

  const tenantAdmin =
    user?.membership_role === "tenant_owner" || user?.membership_role === "tenant_admin";
  const canEditContent = user?.profession_policy?.can_edit_content === true;
  const canManageTeam = tenantAdmin || user?.profession_policy?.can_manage_profession === true;

  const onSetup = location.pathname.includes("/org/setup");
  const onKnowledge = location.pathname.includes("/org/knowledge");
  const onTeam = location.pathname.includes("/org/team");

  if (onTeam && !canManageTeam) {
    return <Navigate to="/org/knowledge" replace />;
  }

  const orgAllowed = tenantAdmin || canEditContent || (onTeam && canManageTeam);
  if (!orgAllowed) {
    return <Navigate to="/" replace />;
  }

  if (user?.org_setup_required && !onSetup) {
    const allowedBeforeSetup = tenantAdmin || (onKnowledge && canEditContent);
    if (!allowedBeforeSetup) {
      return <Navigate to="/org/setup" replace state={{ from: location.pathname }} />;
    }
  }

  return <Outlet />;
}
