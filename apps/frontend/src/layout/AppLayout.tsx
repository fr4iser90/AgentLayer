import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { UserMenu } from "../components/UserMenu";
import { NotificationBell } from "../components/NotificationBell";
import { NotificationProvider } from "../features/notifications/NotificationProvider";
import { GlobalMediaProvider } from "../features/media/GlobalMediaProvider";
import { MediaMiniPlayer } from "../features/media/MediaMiniPlayer";
import { SUPPORTED } from "../i18n/config";

const GITHUB_REPO =
  "https://github.com/fr4iser90/AgentLayer_-_Jetson-Orin-Nano-Super-Developer-Kit-dedicated";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-md px-3 py-2 text-sm transition-colors",
    isActive
      ? "bg-white/10 text-white"
      : "text-surface-muted hover:bg-white/5 hover:text-neutral-200",
  ].join(" ");

const signInClass =
  "rounded-md px-3 py-2 text-sm text-surface-muted hover:bg-white/5 hover:text-neutral-200";

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const { accessToken, user, loading } = useAuth();
  const location = useLocation();
  const signedIn = !!accessToken && !!user;
  const isPublicDashboardShare = location.pathname.includes("/dashboard/shared");

  if (isPublicDashboardShare) {
    return (
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-neutral-950">
        <Outlet />
      </div>
    );
  }

  const shell = (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b border-surface-border bg-surface-raised px-4 py-3">
        <span className="shrink-0 text-sm font-semibold tracking-tight text-white">
          {t("app.title")}
        </span>
        <nav className="flex min-w-0 flex-1 flex-wrap gap-1">
          {loading ? (
            <span className="px-3 py-2 text-xs text-surface-muted">{t("nav.loading")}</span>
          ) : signedIn ? (
            <>
              <NavLink to="/" end className={linkClass}>
                {t("nav.home")}
              </NavLink>
              <NavLink to="/chat" className={linkClass}>
                {t("nav.chat")}
              </NavLink>
              <NavLink to="/studio" className={linkClass}>
                {t("nav.studio")}
              </NavLink>
              <NavLink to="/dashboard" className={linkClass}>
                {t("nav.dashboard")}
              </NavLink>
              <NavLink to="/schedules" className={linkClass}>
                {t("nav.schedules")}
              </NavLink>
              <NavLink to="/tasks" className={linkClass}>
                {t("nav.tasks")}
              </NavLink>
              <NavLink to="/settings/shares" className={linkClass}>
                🔗 {t("nav.shares")}
              </NavLink>
            </>
          ) : (
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <div className="flex gap-1" aria-label={t("language.label")}>
                {SUPPORTED.map((lng) => {
                  const active =
                    i18n.resolvedLanguage?.startsWith(lng) ?? i18n.language.startsWith(lng);
                  return (
                    <button
                      key={lng}
                      type="button"
                      className={[
                        "rounded px-2 py-1 text-[11px] font-medium",
                        active
                          ? "bg-white/15 text-white"
                          : "text-surface-muted hover:bg-white/5 hover:text-neutral-200",
                      ].join(" ")}
                      onClick={() => void i18n.changeLanguage(lng)}
                    >
                      {lng.toUpperCase()}
                    </button>
                  );
                })}
              </div>
              <Link to="/login" className={signInClass}>
                {t("nav.signIn")}
              </Link>
            </div>
          )}
        </nav>
        {loading ? null : signedIn ? (
          <div className="ml-auto flex shrink-0 items-center gap-1">
            <NotificationBell />
            <UserMenu />
          </div>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 overflow-hidden [&>*]:h-full [&>*]:min-h-0">
        <Outlet />
      </div>
      <MediaMiniPlayer />
      <footer className="shrink-0 border-t border-surface-border bg-surface-raised/80 px-4 py-2">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[11px] text-surface-muted">
          <a
            href={GITHUB_REPO}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-neutral-300"
          >
            {t("footer.github")}
          </a>
          <span className="text-white/15" aria-hidden>
            ·
          </span>
          <NavLink to="/docs" className="hover:text-neutral-300">
            {t("footer.docs")}
          </NavLink>
          <span className="text-white/15" aria-hidden>
            ·
          </span>
          <span className="text-white/25">{t("footer.brand")}</span>
        </div>
      </footer>
    </div>
  );

  const wrappedShell = signedIn ? (
    <NotificationProvider enabled={signedIn}>{shell}</NotificationProvider>
  ) : (
    shell
  );

  return <GlobalMediaProvider enabled={signedIn}>{wrappedShell}</GlobalMediaProvider>;
}
