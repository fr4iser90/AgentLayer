import type { ReactNode } from "react";
import { Button } from "./Button";

/**
 * The save bar that stays on screen while a long form is edited.
 *
 * Both existing bars (operator settings, benchmark edit) were the same sticky
 * strip with the same layering and different answers to everything else: one
 * `bg-[#0d0d0d]/95`, the other `bg-[#101010]/95`, one on the lift level, the
 * other on the docked one. A bar that scrolls with content is a stacking
 * decision, and a stacking decision made per file is how a save bar ends up
 * underneath the dialog the form opened.
 *
 * `sticky bottom-0` on the lift level: above the page it belongs to, below the
 * menu, overlay and modal levels — so the bar never covers a dialog opened
 * from the form it saves.
 */

interface StickySaveBarProps {
  /** Save button label — always a verb, never "OK". */
  saveLabel: string;
  onSave?: () => void;
  /** Disabled until something changed. The save button lying about a no-op is worse than a grey button. */
  disabled?: boolean;
  busy?: boolean;
  /** Result of the last save, shown instead of `children` when present. */
  status?: { ok: boolean; text: string } | null;
  /** Standing hint: what saving does, which fields are live immediately. */
  children?: ReactNode;
  /** Extra right-hand action next to save (revert, cancel). */
  secondary?: ReactNode;
  /** The bar is full-bleed by default; pass the page width when the form is narrower. */
  innerClassName?: string;
  className?: string;
}

export function StickySaveBar({
  saveLabel,
  onSave,
  disabled = false,
  busy = false,
  status,
  children,
  secondary,
  innerClassName = "mx-auto max-w-page",
  className = "",
}: StickySaveBarProps) {
  return (
    <div
      className={[
        "sticky bottom-0 z-lift -mx-broad border-t border-line",
        "bg-panel/95 px-broad py-soft backdrop-blur-sm",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className={`${innerClassName} flex flex-wrap items-center justify-between gap-soft`}>
        <div
          className="min-w-0 flex-1 text-label text-ink-muted"
          // A save result is transient information that replaces a static hint;
          // announcing it is the whole point of showing it.
          role={status ? "status" : undefined}
        >
          {status ? (
            <span className={status.ok ? "text-success" : "text-danger"}>{status.text}</span>
          ) : (
            children
          )}
        </div>
        <div className="flex shrink-0 items-center gap-soft">
          {secondary ?? null}
          <Button variant="primary" onClick={onSave} disabled={disabled || busy}>
            {busy ? "…" : saveLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}