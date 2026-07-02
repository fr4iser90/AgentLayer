import { Navigate, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";

/** Platform operator — `/app/admin` (site_admin). */
export function RequireSiteAdmin() {
  const { t } = useTranslation(["auth"]);
  const { accessToken, user, loading } = useAuth();

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

  const siteAdmin =
    user?.site_role === "site_admin" || user?.role?.toLowerCase() === "admin";
  if (!siteAdmin) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
