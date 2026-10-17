import { Link, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { hasRestrictedNav } from "../auth/tenantSurface";
import { NotificationProvider } from "../features/notifications/NotificationProvider";
import { GlobalMediaProvider } from "../features/media/GlobalMediaProvider";
import { MediaMiniPlayer } from "../features/media/MediaMiniPlayer";
import { LegalFooterLinks } from "../components/LegalFooterLinks";
import { AppShell } from "./AppShell";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { surfaceForPath } from "./navModel";

const signInClass =
  "rounded-tile px-soft py-base text-sm text-ink-muted hover:bg-white/5 hover:text-ink-secondary";

/**
 * The chrome for every signed-in surface.
 *
 * Which rail is on screen is decided by `surfaceForPath`, not by nesting another
 * layout with its own sidebar — that is how `/settings/*` and
 * `/admin/interfaces/*` used to end up two and three nav levels deep.
 */
export function AppLayout() {
  const { t } = useTranslation();
  const { accessToken, user, loading } = useAuth();
  const location = useLocation();
  const signedIn = !!accessToken && !!user;
  const showDocsFooter = !signedIn || !hasRestrictedNav(user);
  const isPublicDashboardShare = location.pathname.includes("/dashboard/shared");

  if (isPublicDashboardShare) {
    return (
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-canvas">
        <Outlet />
      </div>
    );
  }

  const surface = surfaceForPath(location.pathname, user);

  // One horizontal row: Impressum · Datenschutz · … · Docs · Brand.
  // flex-nowrap keeps them side-by-side; wrap was the stacked mess.
  const footer = (
    <>
      <MediaMiniPlayer />
      <footer className="shrink-0 border-t border-line bg-panel px-wide py-base">
        <div className="mx-auto flex w-full min-w-0 flex-nowrap items-center justify-center gap-x-wide text-meta text-ink-muted">
          <LegalFooterLinks />
          {showDocsFooter && !signedIn ? (
            <>
              <Link to="/docs" className="shrink-0 hover:text-ink-secondary">
                {t("footer.docs")}
              </Link>
              <span className="shrink-0 text-line-strong" aria-hidden>
                ·
              </span>
            </>
          ) : null}
          <span className="shrink-0 text-ink-muted">{t("footer.brand")}</span>
        </div>
      </footer>
    </>
  );

  // Fill = locked viewport; the page owns inner scroll (chat thread, dashboard
  // canvas, project panes, studio). Everything else — settings/admin/org and
  // document/list app pages (docs, tasks, schedules, …) — uses page scroll on main.
  const fillScroll =
    surface.id === "app" &&
    ["/chat", "/dashboard", "/projects", "/studio"].some(
      (p) => location.pathname === p || location.pathname.startsWith(`${p}/`)
    );

  const shell = (
    <AppShell
      surface={surface}
      signedIn={signedIn && !loading}
      scroll={fillScroll ? "fill" : "page"}
      runningBadge={surface.id === "app"}
      footer={footer}
      signIn={
        <Link to="/login" className={signInClass}>
          {t("nav.signIn")}
        </Link>
      }
    >
      <ErrorBoundary area={`route ${location.pathname}`} resetKey={location.pathname}>
        <Outlet />
      </ErrorBoundary>
    </AppShell>
  );

  const wrappedShell = signedIn ? (
    <NotificationProvider enabled={signedIn}>{shell}</NotificationProvider>
  ) : (
    shell
  );

  return <GlobalMediaProvider enabled={signedIn}>{wrappedShell}</GlobalMediaProvider>;
}