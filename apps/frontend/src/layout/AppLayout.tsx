import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { navItemAllowed, hasRestrictedNav } from "../auth/tenantSurface";
import { UserMenu } from "../components/UserMenu";
import { NotificationBell } from "../components/NotificationBell";
import { NotificationProvider } from "../features/notifications/NotificationProvider";
import { GlobalMediaProvider } from "../features/media/GlobalMediaProvider";
import { MediaMiniPlayer } from "../features/media/MediaMiniPlayer";
import { SUPPORTED } from "../i18n/config";
import { LegalFooterLinks } from "../components/LegalFooterLinks";

const GITHUB_REPO =
  "https://github.com/fr4iser90/AgentLayer_-_Jetson-Orin-Nano-Super-Developer-Kit-dedicated";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-md px-3 py-2 text-sm transition-colors",
    isActive
      ? "bg-white/10 text-white"
      : "text-surface-muted hover:bg-white/5 hover:text-neutral-200",
  ].join(" ");

const menuItemClass =
  "block w-full px-3 py-2 text-left text-sm text-neutral-200 hover:bg-white/10";

const signInClass =
  "rounded-md px-3 py-2 text-sm text-surface-muted hover:bg-white/5 hover:text-neutral-200";

function MoreNavMenu({
  showSchedulesMobile,
  showConnectionsMobile,
  showDashboard,
  showStudio,
  showTasks,
  showShares,
  showDocs,
}: {
  showSchedulesMobile: boolean;
  showConnectionsMobile: boolean;
  showDashboard: boolean;
  showStudio: boolean;
  showTasks: boolean;
  showShares: boolean;
  showDocs: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const hasMobileExtras = showSchedulesMobile || showConnectionsMobile;
  const hasDesktopExtras = showDashboard || showStudio || showTasks || showShares || showDocs;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (!hasMobileExtras && !hasDesktopExtras) return null;

  return (
    <div className={hasDesktopExtras ? "relative" : "relative md:hidden"} ref={rootRef}>
      <button
        type="button"
        className={linkClass({ isActive: open })}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        {t("nav.more")}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute left-0 z-50 mt-1 min-w-[11rem] rounded-lg border border-surface-border bg-[#1a1a1a] py-1 shadow-xl"
        >
          {hasMobileExtras ? (
            <div className="md:hidden">
              {showSchedulesMobile ? (
                <NavLink
                  role="menuitem"
                  to="/schedules"
                  className={menuItemClass}
                  onClick={() => setOpen(false)}
                >
                  {t("nav.schedules")}
                </NavLink>
              ) : null}
              {showConnectionsMobile ? (
                <NavLink
                  role="menuitem"
                  to="/settings/connections"
                  className={menuItemClass}
                  onClick={() => setOpen(false)}
                >
                  {t("nav.connections")}
                </NavLink>
              ) : null}
              {hasDesktopExtras ? <div className="my-1 border-t border-white/10" /> : null}
            </div>
          ) : null}
          {showDashboard ? (
            <NavLink
              role="menuitem"
              to="/dashboard"
              className={menuItemClass}
              onClick={() => setOpen(false)}
            >
              {t("nav.dashboard")}
            </NavLink>
          ) : null}
          {showStudio ? (
            <NavLink
              role="menuitem"
              to="/studio"
              className={menuItemClass}
              onClick={() => setOpen(false)}
            >
              {t("nav.studio")}
            </NavLink>
          ) : null}
          {showTasks ? (
            <NavLink
              role="menuitem"
              to="/tasks"
              className={menuItemClass}
              onClick={() => setOpen(false)}
            >
              {t("nav.tasks")}
            </NavLink>
          ) : null}
          {showShares ? (
            <NavLink
              role="menuitem"
              to="/settings/shares"
              className={menuItemClass}
              onClick={() => setOpen(false)}
            >
              {t("nav.shares")}
            </NavLink>
          ) : null}
          {showDocs ? (
            <NavLink
              role="menuitem"
              to="/docs"
              className={menuItemClass}
              onClick={() => setOpen(false)}
            >
              {t("footer.docs")}
            </NavLink>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const { accessToken, user, loading } = useAuth();
  const location = useLocation();
  const signedIn = !!accessToken && !!user;
  const showDocsFooter = !signedIn || !hasRestrictedNav(user);
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
      <header className="flex shrink-0 items-center gap-3 border-b border-surface-border bg-surface-raised px-4 py-2">
        <span className="shrink-0 text-sm font-semibold tracking-tight text-white">
          {t("app.title")}
        </span>
        <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          {loading ? (
            <span className="px-3 py-2 text-xs text-surface-muted">{t("nav.loading")}</span>
          ) : signedIn ? (
            <>
              {navItemAllowed(user, "chat") ? (
                <NavLink to="/chat" className={linkClass}>
                  {t("nav.chat")}
                </NavLink>
              ) : null}
              {navItemAllowed(user, "schedules") ? (
                <NavLink to="/schedules" className={({ isActive }) => `${linkClass({ isActive })} hidden md:inline-flex`}>
                  {t("nav.schedules")}
                </NavLink>
              ) : null}
              <NavLink
                to="/settings/connections"
                className={({ isActive }) => `${linkClass({ isActive })} hidden md:inline-flex`}
              >
                {t("nav.connections")}
              </NavLink>
              <MoreNavMenu
                showSchedulesMobile={navItemAllowed(user, "schedules")}
                showConnectionsMobile
                showDashboard={navItemAllowed(user, "dashboard")}
                showStudio={navItemAllowed(user, "studio")}
                showTasks={navItemAllowed(user, "tasks")}
                showShares={navItemAllowed(user, "shares")}
                showDocs={showDocsFooter}
              />
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
          <LegalFooterLinks />
          {showDocsFooter && !signedIn ? (
            <>
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
            </>
          ) : null}
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
