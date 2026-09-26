import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * The list of choices behind a "which one?" control.
 *
 * Two were hand-rolled (model catalogue, embedded thread picker). One put
 * `role="option"` on a `<button>` inside `role="listbox"` — the ARIA pattern
 * puts the option role on the element that carries `aria-selected` and is the
 * arrow-key stop, and a button inside an option makes screen readers announce
 * both a list entry and a button. The other nested the option on `<li>` and put
 * the click target on a `<button>` inside it, so `aria-selected` sat on an
 * element nothing could focus.
 *
 * Here the option is the list item itself, it is the tab stop, and selection is
 * a real `onChange`, not a click handler that also closes somebody else's
 * popover.
 */

export interface ListboxOption {
  value: string;
  label: ReactNode;
  /** Secondary line under the label (provider, path, date). */
  hint?: ReactNode;
  disabled?: boolean;
  /** Right-aligned extras (badges). */
  extra?: ReactNode;
}

interface ListboxProps {
  options: ListboxOption[];
  value: string;
  onSelect: (value: string) => void;
  /** Optional: a picker inside a popover usually closes on select. */
  onClose?: () => void;
  ariaLabel: string;
  /** For the trigger's `aria-controls` — without it that attribute dangles. */
  id?: string;
  /** Scrolled height; a listbox that grows forever hides the rest of the page. */
  maxHeight?: string;
  /** Classes the caller owns — placement, width. */
  className?: string;
  empty?: ReactNode;
}

const OPTION = [
  "flex w-full cursor-pointer items-start gap-base rounded-tile px-base py-snug text-left",
  "hover:bg-white/[0.06] focus:outline-none focus-visible:ring-1 focus-visible:ring-accent/50",
  "aria-disabled:pointer-events-none aria-disabled:opacity-45",
].join(" ");

const SELECTED = "bg-accent-subtle text-badge-accent";

export function Listbox({
  options,
  value,
  onSelect,
  onClose,
  ariaLabel,
  id,
  maxHeight = "max-h-[min(240px,40vh)]",
  className = "",
  empty,
}: ListboxProps) {
  const ref = useRef<HTMLUListElement | null>(null);

  // A listbox that opens with focus still on the trigger cannot be walked with
  // arrows: keydown would land on the trigger. Focus starts on the selected
  // option, or the first selectable one.
  useEffect(() => {
    const list = ref.current;
    if (!list) return;
    const rows = Array.from(list.querySelectorAll<HTMLLIElement>('[role="option"]'));
    const chosen =
      rows.find((n) => n.getAttribute("aria-selected") === "true") ??
      rows.find((n) => n.getAttribute("aria-disabled") !== "true");
    chosen?.focus();
  }, []);

  function move(step: number) {
    const nodes = Array.from(ref.current?.querySelectorAll<HTMLLIElement>('[role="option"]') ?? []).filter(
      (n) => n.getAttribute("aria-disabled") !== "true"
    );
    if (nodes.length === 0) return;
    const at = nodes.indexOf(document.activeElement as HTMLLIElement);
    const next = nodes[Math.min(Math.max(at + step, 0), nodes.length - 1)];
    next?.focus();
    // jsdom has no scrollIntoView; the keyboard test must not need a polyfill.
    next?.scrollIntoView?.({ block: "nearest" });
  }

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    switch (event.key) {
      case "Escape":
        event.stopPropagation();
        onClose?.();
        return;
      case "ArrowDown":
        event.preventDefault();
        move(1);
        return;
      case "ArrowUp":
        event.preventDefault();
        move(-1);
        return;
      case "Home":
        event.preventDefault();
        move(-Infinity);
        return;
      case "End":
        event.preventDefault();
        move(Infinity);
        return;
      case "Enter":
      case " ": {
        const active = document.activeElement as HTMLElement;
        const target = active?.getAttribute("data-value");
        if (target == null) return;
        event.preventDefault();
        onSelect(target);
        onClose?.();
        return;
      }
      default:
    }
  }

  return (
    <ul
      ref={ref}
      id={id}
      role="listbox"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={[
        "overflow-y-auto rounded-card border border-line bg-raised py-tight shadow-xl",
        maxHeight,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {options.length === 0 ? (
        <li className="px-soft py-broad text-center text-body text-ink-muted">{empty}</li>
      ) : (
        options.map((option) => {
          const selected = option.value === value;
          return (
            <li
              key={option.value}
              role="option"
              aria-selected={selected}
              aria-disabled={option.disabled || undefined}
              data-value={option.value}
              tabIndex={-1}
              onClick={() => {
                if (option.disabled) return;
                onSelect(option.value);
                onClose?.();
              }}
              className={[OPTION, selected ? SELECTED : "text-ink-primary"]
                .filter(Boolean)
                .join(" ")}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body">{option.label}</span>
                {option.hint ? (
                  <span className="mt-hair block truncate text-meta text-ink-muted">{option.hint}</span>
                ) : null}
              </span>
              {option.extra ? (
                <span className="flex shrink-0 flex-wrap justify-end gap-tight pt-hair">
                  {option.extra}
                </span>
              ) : null}
            </li>
          );
        })
      )}
    </ul>
  );
}