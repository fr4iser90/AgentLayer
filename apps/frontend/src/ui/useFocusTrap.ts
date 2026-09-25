import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Keep Tab inside a floating layer, close it on Escape, and put focus back where
 * it came from.
 *
 * Shared by `Modal` and `Drawer` because a trap that exists in one and not the
 * other is the bug the app already has: six overlays looked like dialogs and
 * none of them held focus, so a keyboard user tabbed out of an open dialog into
 * a page they could no longer see.
 *
 * Visibility is tested with `[hidden]` rather than `offsetParent`. `offsetParent`
 * is `null` for every element in jsdom, so filtering on it makes the trap
 * collect zero candidates and pass its own tests while doing nothing — the same
 * "a green test that cannot go red" failure this repo already documents for its
 * guards.
 */
export function useFocusTrap(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onEscape: () => void
): void {
  // The callback goes in a ref, not the dependency list: callers pass inline
  // arrows, and re-running this effect would restore focus to the trigger and
  // then pull it back into the panel on every keystroke of the parent.
  const dismiss = useRef(onEscape);
  dismiss.current = onEscape;

  useEffect(() => {
    const panel = ref.current;
    if (!active || !panel) return;

    const previous = document.activeElement as HTMLElement | null;
    const candidates = () =>
      Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => !el.closest("[hidden]")
      );

    const first = candidates()[0];
    (first ?? panel).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        dismiss.current();
        return;
      }
      if (event.key !== "Tab") return;
      const list = candidates();
      if (list.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const firstEl = list[0];
      const lastEl = list[list.length - 1];
      const activeEl = document.activeElement;
      // Only wrap when focus is actually inside this layer, so a dialog nested
      // in a drawer does not steal its child's tab order.
      if (!panel.contains(activeEl)) return;
      if (event.shiftKey && (activeEl === firstEl || activeEl === panel)) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && activeEl === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };

    panel.addEventListener("keydown", onKeyDown);
    return () => {
      panel.removeEventListener("keydown", onKeyDown);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [ref, active]);
}