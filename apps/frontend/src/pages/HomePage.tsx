import { Link, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import {
  defaultLandingPath,
  hasRestrictedNav,
  navItemAllowed,
  type NavItemId,
} from "../auth/tenantSurface";

export function HomePage() {
  const { t } = useTranslation(["common"]);
  const { user } = useAuth();
  const restricted = hasRestrictedNav(user);
  const siteAdmin =
    user?.site_role === "site_admin" || user?.role?.toLowerCase() === "admin";

  if (restricted) {
    const cards: { to: string; nav: NavItemId; title: string; desc: string }[] = [];
    if (navItemAllowed(user, "dashboard")) {
      cards.push({
        to: "/dashboard",
        nav: "dashboard",
        title: t("common:nav.dashboard"),
        desc: t("common:home.hubDashboardDesc"),
      });
    }
    if (navItemAllowed(user, "chat")) {
      cards.push({
        to: "/chat",
        nav: "chat",
        title: t("common:nav.chat"),
        desc: t("common:home.hubChatDesc"),
      });
    }
    return (
      <div className="h-full min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-12">
          <h1 className="text-2xl font-semibold text-white">{t("common:home.hubTitle")}</h1>
          <p className="mt-2 text-sm text-surface-muted">{t("common:home.hubIntro")}</p>
          <ul className="mt-8 flex flex-col gap-3">
            {cards.map((c) => (
              <li key={c.nav}>
                <Link
                  to={c.to}
                  className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
                >
                  <span className="font-medium">{c.title}</span>
                  <span className="mt-1 block text-sm text-surface-muted">{c.desc}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <h1 className="text-2xl font-semibold text-white">{t("common:app.title")}</h1>
        <p className="mt-2 text-sm text-surface-muted">
          {t("common:home.intro")}
          {siteAdmin ? (
            <>
              {" "}
              <Link to="/admin" className="text-sky-400 hover:underline">
                {t("common:userMenu.platformAdmin")}
              </Link>
              .
            </>
          ) : null}
        </p>
        <ul className="mt-8 flex flex-col gap-3">
          <li>
            <Link
              to="/chat"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.chat")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.chatDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/studio"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.studio")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.studioDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/tasks"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.tasks")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.tasksDesc")}</span>
            </Link>
          </li>
          <li>
            <Link
              to="/dashboard"
              className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
            >
              <span className="font-medium">{t("common:nav.dashboard")}</span>
              <span className="mt-1 block text-sm text-surface-muted">{t("common:home.dashboardDesc")}</span>
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}

/** Redirect when the current route's nav id is not in the tenant allowlist. */
export function RestrictedNavRedirect({
  nav,
  children,
}: {
  nav: NavItemId;
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!navItemAllowed(user, nav)) {
    return <Navigate to={defaultLandingPath(user)} replace />;
  }
  return <>{children}</>;
}
