import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";
import { isSingleUser } from "./deploymentMode";

/**
 * User management — hidden in `single_user` mode, where there is one account
 * and nobody to administer. Deep-linking `/app/admin/users` there lands back on
 * the admin overview.
 *
 * A UI reduction, not a security boundary: the site-admin guard still sits
 * above this, and the API keeps enforcing `user.manage` regardless of mode.
 */
export function RequireUserAdmin({ children }: { children: ReactNode }) {
  const { t } = useTranslation(["auth"]);
  const { accessToken, user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-4 text-sm text-ink-muted">
        {t("auth:loading")}
      </div>
    );
  }

  if (!accessToken) {
    window.location.replace("/app/login");
    return null;
  }

  if (isSingleUser(user)) {
    return <Navigate to="/admin" replace />;
  }

  return <>{children}</>;
}
