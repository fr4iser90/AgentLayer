/**
 * The one drawer mechanism.
 *
 * Five sheets existed with three different scrim behaviours, and on mobile only
 * one of them was an actual drawer — the rest were chip strips that reflowed.
 * The mobile rule this enforces: an area switch and an area-internal switch
 * share ONE drawer. A surface that shows an area drawer and then a second
 * drawer for its own sections is wrong regardless of how it looks.
 *
 * Escape and scrim tap close it; a leftward swipe closes the right-anchored
 * variant, because that is the gesture a phone user already tries.
 *
 * The collapsible sidebar's mobile drawer was the last overlay outside this
 * file: it hand-rolled a scrim button and a peek-width panel and had none of
 * the above — no dialog role, no Escape, no focus trap — while surviving a
 * resize to desktop as a sheet over the column that had just reappeared. It is
 * a `mobileOnly` `Drawer` now, which is what `mobileOnly` and `flush` exist for.
 */
import { useCallback, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useFocusTrap } from "./useFocusTrap";

export type DrawerSide = "right" | "left" | "bottom";
export type DrawerWidth = "drawer" | "drawerWide";
export type DrawerSurface = "card" | "panel";

const WIDTHS: Record<DrawerWidth, string> = {
  drawer: "md:max-w-drawer",
  drawerWide: "md:max-w-drawerWide",
};

// A drawer that floats content over the page paints a content container. A
// drawer that stands in for chrome — the app rail, a page sidebar — paints the
// surface of the region it replaces, so the same list does not change colour
// when the breakpoint does. The primitive picks the class rather than letting
// `className` override it: two `bg-*` utilities have the same specificity, and
// Tailwind decides that by stylesheet order, not by the order they are written
// on the element — an override that happens to win today loses next time the
// palette is rebuilt.
const SURFACES: Record<DrawerSurface, string> = {
  card: "bg-card",
  panel: "bg-panel",
};

const ANCHOR: Record<DrawerSide, string> = {
  right: "inset-y-0 right-0 w-full md:w-1/2",
  left: "inset-y-0 left-0 w-full md:w-1/2",
  bottom: "inset-x-0 bottom-0 w-full",
};

const SWIPE_THRESHOLD_PX = 60;

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  side?: DrawerSide;
  width?: DrawerWidth;
  surface?: DrawerSurface;
  /**
   * Hide the sheet from `md` up. For a drawer that REPLACES a desktop region
   * instead of adding a sheet over it: without it, resizing to desktop while
   * the sheet is open leaves two navigations on screen, the hidden one still
   * holding the focus trap. `mobileOnly` makes the desktop region win; the
   * stale open state behind it is inert and Escape clears it.
   */
  mobileOnly?: boolean;
  /**
   * The content owns its padding and its scrolling. A prose body wants the
   * drawer's padding and one scroll container; a sidebar list has a pinned
   * header and its own scroll area, and wrapping it in a padded scrolling div
   * gives it two scrollbars and scrolls the pinned part away.
   */
  flush?: boolean;
  children?: ReactNode;
  /**
   * Pinned content between the title row and the scrolling body — a tab strip,
   * a subtitle. Anything that has to stay reachable while the body scrolls.
   * Without this slot a caller either loses those controls on scroll or grows a
   * second header beside this one.
   */
  headerExtra?: ReactNode;
  footer?: ReactNode;
  className?: string;
  /**
   * Accessible name of the close control. Defaults to the shared "Close panel";
   * a caller whose panel is one of several on the page names it ("Close chat
   * list"), because "panel" is unambiguous on screen and not out of a
   * screen reader.
   */
  closeLabel?: string;
}

export function Drawer({
  open,
  onClose,
  title,
  side = "right",
  width = "drawer",
  surface = "card",
  mobileOnly = false,
  flush = false,
  children,
  headerExtra,
  footer,
  className,
  closeLabel,
}: DrawerProps) {
  const { t } = useTranslation("common");
  const panelRef = useRef<HTMLDivElement>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  // Same contract as the dialog: focus in, Tab held inside, Escape and focus
  // restore out. A drawer that closes on Escape but lets Tab escape it is only
  // half a modal.
  useFocusTrap(panelRef, open, onClose);

  // Only a right-anchored drawer swipes shut: swiping left over a bottom sheet
  // or a left rail means something else (going back, dismissing a keyboard).
  const onTouchStart = useCallback(
    (event: React.TouchEvent) => {
      if (side !== "right") return;
      const touch = event.touches[0];
      touchStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
    },
    [side]
  );

  const onTouchEnd = useCallback(
    (event: React.TouchEvent) => {
      const start = touchStart.current;
      touchStart.current = null;
      if (!start) return;
      const touch = event.changedTouches[0];
      if (!touch) return;
      const dx = start.x - touch.clientX;
      const dy = Math.abs(start.y - touch.clientY);
      if (dx >= SWIPE_THRESHOLD_PX && dy < dx) onClose();
    },
    [onClose]
  );

  if (!open) return null;

  return (
    <div
      className={["fixed inset-0 z-overlay bg-overlay", mobileOnly ? "md:hidden" : ""]
        .filter(Boolean)
        .join(" ")}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        className={[
          "absolute flex max-h-full flex-col overflow-hidden shadow-overlay outline-none",
          SURFACES[surface],
          "border-line md:border",
          ANCHOR[side],
          WIDTHS[width],
          side === "bottom" ? "border-t" : "md:border-y-0",
          side === "right" ? "md:border-l" : "",
          side === "left" ? "md:border-r" : "",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <header className="flex shrink-0 items-start gap-soft border-b border-line px-roomy py-soft">
          <h2 className="min-w-0 flex-1 text-title text-ink-primary">{title}</h2>
          <button
            type="button"
            aria-label={closeLabel ?? t("drawer.close")}
            onClick={onClose}
            className="shrink-0 rounded-tile p-tight text-ink-muted hover:bg-white/10 hover:text-ink-primary"
          >
            <X size={16} aria-hidden />
          </button>
        </header>
        {headerExtra ? (
          <div className="shrink-0 px-roomy pb-soft">{headerExtra}</div>
        ) : null}
        <div
          className={
            flush
              ? "flex min-h-0 flex-1 flex-col overflow-hidden"
              : "min-h-0 flex-1 overflow-y-auto overscroll-contain px-roomy py-soft"
          }
        >
          {children}
        </div>
        {footer ? (
          <footer className="flex shrink-0 items-center justify-end gap-base border-t border-line px-roomy py-soft">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}