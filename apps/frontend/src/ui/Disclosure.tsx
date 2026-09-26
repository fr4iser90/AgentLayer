import { useId, useState, type ReactNode } from "react";

/**
 * Expand / collapse.
 *
 * Seven places in the app hide content behind a click. Three were
 * `<details>/<summary>` — correct semantics, but each re-implemented the marker
 * removal (`list-none`, `marker:content-none`, `::-webkit-details-marker`, a
 * `group-open:` dance just to swap the word "expand" for "collapse"). Four were
 * a `useState` plus a `<button>` with no `aria-expanded` at all, so nothing told
 * a screen reader whether the click had done anything.
 *
 * One component, real `aria-expanded` / `aria-controls`, a chevron that rotates
 * instead of a word that swaps, and it works both uncontrolled and driven from
 * outside (a filter panel that must remember its state across routes).
 */

interface DisclosureProps {
  title: ReactNode;
  children: ReactNode;
  /** `row` spans the width (panels, groups); `chip` hugs its content (inline badges). */
  variant?: "row" | "chip";
  /** Hue of a chip. `neutral` for "more detail", the others to match what is hidden. */
  tone?: "neutral" | "accent" | "warning";
  defaultOpen?: boolean;
  /** Pass to drive it from outside; omit for a self-contained disclosure. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Small text after the title (counts, sizes) — stays visible when collapsed. */
  meta?: ReactNode;
  /** Node before the title (a status dot). */
  leading?: ReactNode;
  /**
   * Word that says what the click does, swapped with state. A rotated chevron is
   * the visual cue, but the word is what a screenshot reader and a low-vision
   * user get, and it is the only part a chevron cannot carry.
   */
  hint?: { open: string; closed: string };
  className?: string;
  bodyClassName?: string;
}

const CHIP_TONES: Record<NonNullable<DisclosureProps["tone"]>, string> = {
  neutral: "border-line bg-white/[0.04] text-ink-secondary hover:bg-white/[0.07]",
  accent: "border-accent/35 bg-accent-subtle text-badge-accent hover:bg-accent/15",
  warning: "border-warning/35 bg-warning-subtle text-badge-warning hover:bg-warning/15",
};

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-3.5 w-3.5 shrink-0 transition-transform duration-fast ease-standard ${
        open ? "rotate-180" : ""
      }`}
    >
      <path d="m5 8 5 5 5-5" />
    </svg>
  );
}

export function Disclosure({
  title,
  children,
  variant = "row",
  tone = "neutral",
  defaultOpen = false,
  open,
  onOpenChange,
  meta,
  leading,
  hint,
  className = "",
  bodyClassName = "",
}: DisclosureProps) {
  const [internal, setInternal] = useState(defaultOpen);
  const panelId = useId();
  const isOpen = open ?? internal;

  function toggle() {
    const next = !isOpen;
    if (open === undefined) setInternal(next);
    onOpenChange?.(next);
  }

  const trigger = [
    "inline-flex cursor-pointer items-center gap-snug rounded-tile",
    "focus:outline-none focus-visible:shadow-focus",
    variant === "chip" ? `border px-base py-tight text-meta ${CHIP_TONES[tone]}` : "",
    variant === "row" ? "w-full justify-between gap-base px-soft py-base text-body" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={toggle}
        className={trigger}
      >
        <span className="flex min-w-0 flex-1 items-center gap-snug">
          {leading ?? null}
          <span className="truncate">{title}</span>
          {meta ? <span className="shrink-0 text-meta font-normal opacity-80">{meta}</span> : null}
        </span>
        {hint ? (
          // The word is swapped, not hidden with the panel: it is the label of
          // the control, and a control whose label changes meaning when pressed
          // is what `aria-expanded` exists to describe — the visible text and
          // the announced state have to agree.
          <span className="shrink-0 text-meta font-normal opacity-80">
            {isOpen ? hint.open : hint.closed}
          </span>
        ) : null}
        <Chevron open={isOpen} />
      </button>
      {isOpen ? (
        <div id={panelId} className={`mt-base ${bodyClassName}`.trim()}>
          {children}
        </div>
      ) : null}
    </div>
  );
}