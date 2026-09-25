import { useEffect, useRef, type RefObject } from "react";

/**
 * Dismiss an anchored popover when the pointer goes outside it.
 *
 * Five verbatim copies of this existed, listening to three different events
 * (`mousedown` x3, `pointerdown` x1), and one of the five popovers had no
 * dismissal at all. `pointerdown` is the one worth keeping: it fires for mouse,
 * touch and pen, and unlike `mousedown` it does not arrive a second time as a
 * synthetic event after a tap — which is what made the `mousedown` variants
 * close a menu and immediately reopen it on phones.
 *
 * Escape is handled here too, because every one of those popovers needs it and
 * three of them had forgotten.
 */
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  onOutside: () => void,
  enabled = true
): void {
  // Keep the latest callback in a ref so a caller passing an inline arrow does
  // not re-subscribe a document listener on every render.
  const handler = useRef(onOutside);
  handler.current = onOutside;

  useEffect(() => {
    if (!enabled) return;
    const onPointer = (event: PointerEvent) => {
      const el = ref.current;
      if (!el) return;
      if (!el.contains(event.target as Node)) handler.current();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") handler.current();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref, enabled]);
}