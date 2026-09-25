import { Navigate, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";
import { defaultLandingPath } from "./tenantSurface";
import { isSiteAdmin } from "../pages/admin/accessGating";

/** Platform operator — `/app/admin` (site_admin). */
export function RequireSiteAdmin() {
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

  const siteAdmin = isSiteAdmin(user);
  if (!siteAdmin) {
    return <Navigate to={defaultLandingPath(user)} replace />;
  }

  return <Outlet />;
}
