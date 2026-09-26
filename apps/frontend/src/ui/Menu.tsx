import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * The dropdown menu surface.
 *
 * Three menus were hand-drawn (user menu, notification bell, sidebar "more")
 * and had drifted apart in exactly the ways a shared surface exists to stop:
 * one filled `bg-raised`, the others `#1a1a1a` / `#141414`; all three declared
 * `role="menu"` but none moved focus into it, so opening with the keyboard left
 * focus on the trigger and Tab walked out of the open menu into the page
 * behind it. Focus lands on the first item, Tab wraps inside, arrows walk the
 * list, Escape closes — the WAI-ARIA menu pattern.
 */

export interface MenuItem {
  id: string;
  label: ReactNode;
  onSelect?: () => void;
  disabled?: boolean;
  /** Destructive item (sign out, delete). Kept as a flag, not a class. */
  tone?: "danger";
}

interface MenuProps {
  items: MenuItem[];
  onClose: () => void;
  /** Which edge lines up with the trigger. Menus anchored to the right need `end`. */
  align?: "start" | "end";
  /** Sizing classes owned by the caller — width is the one thing a menu cannot guess. */
  width?: string;
  header?: ReactNode;
  footer?: ReactNode;
  className?: string;
  /** Pass `false` when the menu opens on hover and focus must stay where it was. */
  autoFocus?: boolean;
}

const ITEM = [
  "flex w-full items-center gap-base px-soft py-base text-left text-body",
  "text-ink-secondary hover:bg-white/[0.06] hover:text-ink-primary",
  "focus:outline-none focus-visible:bg-white/10 focus-visible:text-ink-primary",
  "disabled:pointer-events-none disabled:opacity-45",
].join(" ");

export function Menu({
  items,
  onClose,
  align = "end",
  width = "min-w-[12rem]",
  header,
  footer,
  className = "",
  autoFocus = true,
}: MenuProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!autoFocus) return;
    ref.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not([disabled])')?.focus();
  }, [autoFocus]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const nodes = Array.from(
      ref.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])') ?? []
    );
    if (nodes.length === 0) return;
    event.preventDefault();
    const at = nodes.indexOf(document.activeElement as HTMLButtonElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    nodes[(at + step + nodes.length) % nodes.length]?.focus();
  }

  return (
    <div
      ref={ref}
      role="menu"
      onKeyDown={onKeyDown}
      className={[
        "absolute z-menu mt-tight overflow-hidden rounded-card border border-line",
        // One fill for every menu: `bg-raised` (#1A1C20) is the token for a
        // surface floated over the page, the raw hexes were the same colour by
        // eye and different by value.
        "bg-raised py-tight shadow-xl",
        align === "end" ? "right-0" : "left-0",
        width,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {header ?? null}
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          disabled={item.disabled}
          onClick={() => {
            onClose();
            item.onSelect?.();
          }}
          className={[ITEM, item.tone === "danger" ? "text-badge-danger hover:text-badge-danger" : ""]
            .filter(Boolean)
            .join(" ")}
        >
          {item.label}
        </button>
      ))}
      {footer ?? null}
    </div>
  );
}