/**
 * Tooltip — the accessible hover/focus bubble for icon-only and truncated UI.
 *
 * The concept makes this a prerequisite rather than a nicety: principle 3 says an
 * icon may replace text only where it is unambiguous, and a tooltip is what makes
 * "navigation with icons" honest. 109 native `title=` attributes are in the tree
 * today (50 on buttons, 31 on spans), which means the app already depends on
 * tooltips but renders them with the browser's own — uncontrollable delay, no
 * theming, no keyboard contract, clipped by any scrolling ancestor.
 *
 * Three properties this implementation is built around, and why each one is not
 * optional:
 *
 * 1. **Portalled to document.body.** The existing popovers (UserMenu,
 *    NotificationBell) use `absolute` inside a `relative` wrapper. For a menu
 *    that is fine. For a tooltip it is not: the 109 targets live inside the chat
 *    transcript and tables with `overflow-x-auto`, where an absolutely positioned
 *    child is clipped by the scroll container. A portal removes the whole class
 *    of bug rather than working around it per site.
 *
 * 2. **Hoverable, per WCAG 1.4.13.** The pointer must be able to travel from
 *    trigger to bubble without the bubble vanishing, so hiding is delayed by a
 *    grace window and cancelled when the pointer arrives on the bubble itself.
 *    Without this, a tooltip containing a link is unusable.
 *
 * 3. **Dismissable by Escape, per WCAG 1.4.13.** Escape closes it and returns
 *    focus to the trigger, so a keyboard user is never trapped in content they
 *    did not open.
 *
 * Touch is deliberately excluded: `onPointerEnter` is checked for
 * `pointerType === "touch"` and never opens the bubble. Hover-only content must
 * not be essential content, and a tap-to-open tooltip on a button fights the
 * button's own action.
 *
 * The hover delay exists because without it a tooltip fires on every pass of the
 * mouse across a toolbar. Focus shows immediately — a keyboard user asked for it.
 */
import {
  Children,
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

export type TooltipPlacement = "top" | "bottom" | "left" | "right";

/** Gap between trigger and bubble. */
export const GAP = 6;
/** Minimum distance kept from the viewport edge. */
export const EDGE = 8;
/** Delay before a hover opens the bubble. */
export const HOVER_DELAY = 500;
/** Grace window so the pointer can cross the gap onto the bubble. */
export const HIDE_DELAY = 120;
/**
 * How long after a touch a hover is still ignored. Real touch devices emit a
 * synthetic mouseenter (and often a pointerenter) after tap, so a touch-only
 * check on `pointerType` alone is not enough — and jsdom has no PointerEvent
 * constructor at all, which makes `pointerType` undefined there and the
 * timestamp guard the only touch signal that is testable in a unit test.
 */
export const TOUCH_SUPPRESS_MS = 700;

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const OPPOSITE: Record<TooltipPlacement, TooltipPlacement> = {
  top: "bottom",
  bottom: "top",
  left: "right",
  right: "left",
};

/**
 * Compute where the bubble goes, flipping to the opposite side when the preferred
 * side has no room. Pure on purpose: jsdom performs no layout, so
 * getBoundingClientRect() is all zeros there and the only way to test placement
 * at all is to test the arithmetic directly.
 *
 * The cross axis is always clamped back inside the viewport, so a bubble wider
 * than the space left of centre on a narrow screen still lands fully on screen.
 */
export function place(
  trigger: Rect,
  tip: { width: number; height: number },
  viewport: { width: number; height: number },
  placement: TooltipPlacement,
  gap: number = GAP,
  edge: number = EDGE,
): { top: number; left: number; placement: TooltipPlacement } {
  const fits: Record<TooltipPlacement, boolean> = {
    top: trigger.y - tip.height - gap >= edge,
    bottom: trigger.y + trigger.height + gap + tip.height <= viewport.height - edge,
    left: trigger.x - tip.width - gap >= edge,
    right: trigger.x + tip.width + gap <= viewport.width - edge,
  };

  const chosen: TooltipPlacement = fits[placement]
    ? placement
    : fits[OPPOSITE[placement]]
      ? OPPOSITE[placement]
      : placement;

  let top: number;
  let left: number;
  if (chosen === "top") {
    top = trigger.y - tip.height - gap;
    left = trigger.x + trigger.width / 2 - tip.width / 2;
  } else if (chosen === "bottom") {
    top = trigger.y + trigger.height + gap;
    left = trigger.x + trigger.width / 2 - tip.width / 2;
  } else if (chosen === "left") {
    top = trigger.y + trigger.height / 2 - tip.height / 2;
    left = trigger.x - tip.width - gap;
  } else {
    top = trigger.y + trigger.height / 2 - tip.height / 2;
    left = trigger.x + trigger.width + gap;
  }

  const maxLeft = Math.max(edge, viewport.width - tip.width - edge);
  const maxTop = Math.max(edge, viewport.height - tip.height - edge);
  return {
    top: Math.min(Math.max(top, edge), maxTop),
    left: Math.min(Math.max(left, edge), maxLeft),
    placement: chosen,
  };
}

/**
 * `:focus-visible` gating, so a mouse click does not raise a tooltip the user
 * did not ask for. jsdom does not implement the selector and throws rather than
 * returning false; showing in that case keeps component tests meaningful instead
 * of silently testing nothing.
 */
function focusVisible(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  try {
    return target.matches(":focus-visible");
  } catch {
    return true;
  }
}

function composeRefs<T>(...refs: unknown[]): (node: T | null) => void {
  return (node: T | null) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === "function") (ref as (n: T | null) => void)(node);
      else (ref as { current: T | null }).current = node;
    }
  };
}

export interface TooltipProps {
  /** The bubble content. Empty or absent renders the child untouched. */
  label?: ReactNode;
  placement?: TooltipPlacement;
  children: ReactNode;
}

export function Tooltip({ label, placement = "top", children }: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{
    top: number;
    left: number;
    placement: TooltipPlacement;
  } | null>(null);

  const triggerRef = useRef<HTMLElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const showTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const touchAt = useRef(0);

  const clearTimers = useCallback(() => {
    if (showTimer.current !== null) clearTimeout(showTimer.current);
    if (hideTimer.current !== null) clearTimeout(hideTimer.current);
    showTimer.current = null;
    hideTimer.current = null;
  }, []);

  const hide = useCallback(() => {
    clearTimers();
    setOpen(false);
  }, [clearTimers]);

  const scheduleHide = useCallback(() => {
    if (showTimer.current !== null) clearTimeout(showTimer.current);
    showTimer.current = null;
    if (hideTimer.current !== null) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setOpen(false), HIDE_DELAY);
  }, []);

  const measure = useCallback(() => {
    const trigger = triggerRef.current;
    const tip = tipRef.current;
    if (!trigger || !tip) return;
    const tr = trigger.getBoundingClientRect();
    const tp = tip.getBoundingClientRect();
    setPos(
      place(
        { x: tr.x, y: tr.y, width: tr.width, height: tr.height },
        { width: tp.width, height: tp.height },
        { width: window.innerWidth, height: window.innerHeight },
        placement,
      ),
    );
  }, [placement]);

  // Position before paint so the bubble never flashes at the wrong coordinates.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    measure();
  }, [open, measure]);

  // Keep the bubble attached while the page scrolls or the viewport resizes.
  useEffect(() => {
    if (!open) return;
    const onMove = () => measure();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open, measure]);

  // Escape dismisses and hands focus back, so a keyboard user is not stranded.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      hide();
      triggerRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, hide]);

  useEffect(() => clearTimers, [clearTimers]);

  const hasLabel = label !== undefined && label !== null && label !== "";
  const child = Children.only(children) as ReactElement<Record<string, unknown>> | null;

  // No label means nothing to say: hand back the child with no handlers, no
  // aria-describedby and no portal, so a conditional `label={x ? "…" : ""}`
  // costs nothing rather than leaving a dangling aria reference.
  if (!hasLabel || !isValidElement(child)) return <>{children}</>;

  const original = child.props as Record<string, ((...a: unknown[]) => void) | undefined>;

  const handlers: Record<string, unknown> = {
    onTouchStart: (e: React.TouchEvent) => {
      original.onTouchStart?.(e);
      touchAt.current = Date.now();
      // A tap on a control the tooltip was describing should not leave the
      // bubble floating over whatever the tap just did.
      hide();
    },
    onPointerEnter: (e: React.PointerEvent) => {
      original.onPointerEnter?.(e);
      // Touch never opens a hover bubble; a tap would fight the control's action.
      if (e.pointerType === "touch") return;
      if (Date.now() - touchAt.current < TOUCH_SUPPRESS_MS) return;
      if (hideTimer.current !== null) clearTimeout(hideTimer.current);
      hideTimer.current = null;
      if (showTimer.current !== null) clearTimeout(showTimer.current);
      showTimer.current = setTimeout(() => setOpen(true), HOVER_DELAY);
    },
    onPointerLeave: (e: React.PointerEvent) => {
      original.onPointerLeave?.(e);
      if (e.pointerType === "touch") return;
      scheduleHide();
    },
    onFocus: (e: React.FocusEvent) => {
      original.onFocus?.(e);
      if (!focusVisible(e.target)) return;
      clearTimers();
      setOpen(true);
    },
    onBlur: (e: React.FocusEvent) => {
      original.onBlur?.(e);
      hide();
    },
    "aria-describedby": open ? id : undefined,
  };

  const ref = composeRefs<HTMLElement>(
    triggerRef,
    (child as unknown as { ref?: unknown }).ref,
  );

  return (
    <>
      {cloneElement(child, { ...handlers, ref })}
      {open
        ? createPortal(
            <div
              ref={tipRef}
              id={id}
              role="tooltip"
              style={{
                top: pos ? pos.top : 0,
                left: pos ? pos.left : 0,
                visibility: pos ? "visible" : "hidden",
              }}
              className="animate-tooltip-in fixed z-tooltip max-w-chipWide rounded-tile border border-line bg-raised px-base py-tight text-label text-ink-primary shadow-raised"
              onPointerEnter={() => {
                if (hideTimer.current !== null) clearTimeout(hideTimer.current);
                hideTimer.current = null;
              }}
              onPointerLeave={scheduleHide}
            >
              {label}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
