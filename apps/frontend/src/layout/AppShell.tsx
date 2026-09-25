import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PanelLeft } from "lucide-react";
import { Mascot } from "../ui/Mascot";
import { NavRail } from "../ui/NavRail";
import { Drawer } from "../ui/Drawer";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { UserMenu } from "../components/UserMenu";
import { NotificationBell } from "../components/NotificationBell";
import { AgentRunningBadge } from "../features/chat/AgentRunningBadge";
import type { NavSurface } from "./navModel";

interface AppShellProps {
  surface: NavSurface;
  signedIn: boolean;
  /** Shown in the chrome slot while signed out. */
  signIn?: ReactNode;
  /**
   * `fill` — the page owns its scrolling (chat, dashboards). `page` — the shell
   * scrolls (settings, admin, org), which is what those pages were mounted in
   * before the rail existed and what they still assume.
   */
  scroll?: "fill" | "page";
  /** The running-agent pill belongs to the app surface; admin has its own traces. */
  runningBadge?: boolean;
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * The single application chrome.
 *
 * One header with the mascot, the language switch and the account controls, one
 * rail, one drawer. `AppLayout`, `SettingsLayout`, `AdminLayout`,
 * `OrgAdminLayout` and `InterfacesLayout` all render through here, so an
 * operator in `/admin/interfaces/voice` has the same avatar, bell and language
 * control as a user in `/chat` — previously the admin surfaces had none of
 * them, and leaving meant hunting for a small text link.
 */
export function AppShell({
  surface,
  signedIn,
  signIn,
  scroll = "fill",
  runningBadge = false,
  footer,
  children
}: AppShellProps) {
  const { t } = useTranslation([surface.namespace, "common"]);
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Navigating closes the drawer: on a phone the rail covers the page you just
  // asked for, and leaving it open makes the next tap a second navigation.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // The drawer always needs a name; the app rail has no heading of its own.
  const title = surface.titleKey
    ? t(surface.titleKey, { ns: surface.namespace })
    : t("nav.sectionsAria", { ns: "common" });

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-canvas">
      <header className="flex shrink-0 items-center gap-soft border-b border-line bg-panel px-wide py-base">
        <button
          type="button"
          className="shrink-0 rounded-tile p-tight text-ink-muted hover:bg-white/5 hover:text-ink-primary md:hidden"
          aria-label={t("nav.openMenu", { ns: "common" })}
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          <PanelLeft size={18} aria-hidden />
        </button>
        <Link to="/" className="flex shrink-0 items-center gap-snug">
          <Mascot size={28} animated={false} ariaLabel={t("app.title", { ns: "common" })} />
          <span className="text-sm font-semibold tracking-tight text-ink-primary">
            {t("app.title", { ns: "common" })}
          </span>
        </Link>
        <div className="ml-auto flex shrink-0 items-center gap-tight">
          {runningBadge && signedIn ? <AgentRunningBadge /> : null}
          <LanguageSwitch />
          {signedIn ? (
            <>
              <NotificationBell />
              <UserMenu />
            </>
          ) : (
            signIn
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="hidden w-56 shrink-0 overflow-y-auto overscroll-contain border-r border-line bg-panel px-soft py-wide md:block">
          {surface.titleKey ? (
            <p className="mb-base px-base text-meta font-medium uppercase tracking-wide text-ink-muted">
              {title}
            </p>
          ) : null}
          <NavRail surface={surface} />
        </aside>
        <main
          className={[
            "min-h-0 min-w-0 flex-1",
            scroll === "page"
              ? "overflow-y-auto overscroll-contain"
              : "overflow-hidden [&>*]:h-full [&>*]:min-h-0"
          ].join(" ")}
        >
          {children}
        </main>
      </div>

      {footer}

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={title}
        side="left"
        surface="panel"
        mobileOnly
      >
        <NavRail surface={surface} />
      </Drawer>
    </div>
  );
}