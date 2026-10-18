import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PanelLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Mascot } from "../ui/Mascot";
import { NavRail } from "../ui/NavRail";
import { Drawer } from "../ui/Drawer";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { UserMenu } from "../components/UserMenu";
import { NotificationBell } from "../components/NotificationBell";
import { AgentRunningBadge } from "../features/chat/AgentRunningBadge";
import type { NavSurface } from "./navModel";
import { Button } from "../ui/Button";
import { Tooltip } from "../ui/Tooltip";

const RAIL_PIN_KEY = "agent-ui.navRailPinned";
/** Grace before collapsing a hover-peek so the pointer can cross into the panel. */
const PEEK_LEAVE_MS = 180;

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
  /**
   * Page mounts a context sidebar (chat threads, boards, …). The app rail
   * collapses to icons so both columns fit; hover peeks labels, pin keeps wide.
   */
  contextNav?: boolean;
  /** The running-agent pill belongs to the app surface; admin has its own traces. */
  runningBadge?: boolean;
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * The single application chrome.
 *
 * Signed-in: header + rail + main + footer.
 * Signed-out (login / setup / legal): header + main + footer, no rail — those
 * destinations need a session.
 */
export function AppShell({
  surface,
  signedIn,
  signIn,
  scroll = "fill",
  contextNav = false,
  runningBadge = false,
  footer,
  children
}: AppShellProps) {
  const { t } = useTranslation([surface.namespace, "common"]);
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [navFolds, setNavFolds] = useState<Record<string, boolean>>({});
  const foldDoor = (to: string, open: boolean) =>
    setNavFolds((current) => ({ ...current, [to]: open }));

  const [pinned, setPinned] = useState(() => {
    try {
      return localStorage.getItem(RAIL_PIN_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [peek, setPeek] = useState(false);
  const peekLeaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setDrawerOpen(false);
    setPeek(false);
  }, [location.pathname]);

  useEffect(() => {
    return () => {
      if (peekLeaveTimer.current) clearTimeout(peekLeaveTimer.current);
    };
  }, []);

  const title = surface.titleKey
    ? t(surface.titleKey, { ns: surface.namespace })
    : t("nav.sectionsAria", { ns: "common" });

  const showRail = signedIn;
  /** In-flow width: icon rail when context nav is up and the user has not pinned. */
  const layoutCompact = contextNav && !pinned;
  /** Labels visible: full rail, pinned, or hover/focus peek. */
  const showLabels = !layoutCompact || peek;

  const mainClass = [
    "min-h-0 min-w-0 flex-1",
    scroll === "page"
      ? "overflow-y-auto overscroll-contain"
      : "overflow-hidden [&>*]:h-full [&>*]:min-h-0"
  ].join(" ");

  function persistPin(next: boolean) {
    setPinned(next);
    try {
      localStorage.setItem(RAIL_PIN_KEY, next ? "1" : "0");
    } catch {
      /* ignore quota / private mode */
    }
    if (next) setPeek(false);
  }

  function onRailEnter() {
    if (!layoutCompact) return;
    if (peekLeaveTimer.current) {
      clearTimeout(peekLeaveTimer.current);
      peekLeaveTimer.current = null;
    }
    setPeek(true);
  }

  function onRailLeave() {
    if (!layoutCompact) return;
    if (peekLeaveTimer.current) clearTimeout(peekLeaveTimer.current);
    peekLeaveTimer.current = setTimeout(() => setPeek(false), PEEK_LEAVE_MS);
  }

  const railInner = (
    <>
      {surface.titleKey && showLabels ? (
        <p className="mb-base px-base text-meta font-medium uppercase tracking-wide text-ink-muted">
          {title}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <NavRail
          surface={surface}
          folds={navFolds}
          onFold={foldDoor}
          compact={!showLabels}
        />
      </div>
      {contextNav ? (
        <div className={`mt-soft shrink-0 border-t border-line pt-soft ${showLabels ? "px-soft" : "px-tight"}`}>
          <Tooltip
            label={pinned ? t("nav.unpinRail", { ns: "common" }) : t("nav.pinRail", { ns: "common" })}
            placement="right"
          >
            <Button
              variant="ghost"
              type="button"
              className={[
                "w-full text-ink-muted hover:bg-white/5 hover:text-ink-primary",
                showLabels ? "justify-start gap-snug px-base py-base text-sm" : "justify-center p-base",
              ].join(" ")}
              aria-pressed={pinned}
              aria-label={pinned ? t("nav.unpinRail", { ns: "common" }) : t("nav.pinRail", { ns: "common" })}
              onClick={() => persistPin(!pinned)}
            >
              {pinned ? (
                <PanelLeftClose size={16} aria-hidden className="shrink-0" />
              ) : (
                <PanelLeftOpen size={16} aria-hidden className="shrink-0" />
              )}
              {showLabels ? (
                <span className="truncate">
                  {pinned ? t("nav.unpinRail", { ns: "common" }) : t("nav.pinRail", { ns: "common" })}
                </span>
              ) : null}
            </Button>
          </Tooltip>
        </div>
      ) : null}
    </>
  );

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-canvas">
      <header className="flex shrink-0 items-center gap-soft border-b border-line bg-panel px-wide py-base">
        {showRail ? (
          <Button
            variant="ghost"
            type="button"
            className="shrink-0 p-tight text-ink-muted hover:bg-white/5 hover:text-ink-primary md:hidden"
            aria-label={t("nav.openMenu", { ns: "common" })}
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            <PanelLeft size={18} aria-hidden />
          </Button>
        ) : null}
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

      {showRail ? (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/*
            Gutter stays w-14 when compact so main does not jump on hover.
            Peek paints an expanded overlay over the gutter + a slice of main.
          */}
          <div
            className={[
              "relative hidden shrink-0 md:block",
              layoutCompact ? "w-14" : "w-56",
            ].join(" ")}
            onMouseEnter={onRailEnter}
            onMouseLeave={onRailLeave}
            onFocus={onRailEnter}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
                onRailLeave();
              }
            }}
          >
            <aside
              className={[
                "flex h-full min-h-0 flex-col border-r border-line bg-panel py-wide",
                layoutCompact && peek
                  ? "absolute inset-y-0 left-0 z-docked w-56 px-soft shadow-raised"
                  : layoutCompact
                    ? "w-14 px-tight"
                    : "w-56 px-soft",
              ].join(" ")}
            >
              {railInner}
            </aside>
          </div>
          <main className={mainClass}>{children}</main>
        </div>
      ) : (
        <main className={mainClass}>{children}</main>
      )}

      {footer}

      {showRail ? (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          title={title}
          side="left"
          surface="panel"
          mobileOnly
        >
          <NavRail surface={surface} folds={navFolds} onFold={foldDoor} />
        </Drawer>
      ) : null}
    </div>
  );
}
