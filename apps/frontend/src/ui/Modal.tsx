/**
 * The dialog primitive.
 *
 * Measured before this file existed: 16 `fixed inset-0` overlays in the app,
 * of which 6 are visually a modal and semantically not one; a focus trap
 * existed nowhere in the codebase; and 4 of the 10 overlays that did declare
 * `role="dialog"` had no Escape handler. That combination is not cosmetic —
 * keyboard and screen-reader users could Tab out of an open dialog into the
 * page behind it, which is invisible to them.
 *
 * Rendered in place rather than portalled, matching the stacking note in
 * `tailwind.config.js`: a dialog that renders where it is called contains its
 * own descendants, which is why `tooltip` can sit above `modal` without a
 * tooltip inside a dialog disappearing.
 */
import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useFocusTrap } from "./useFocusTrap";

export type ModalSize = "dialog" | "dialogWide" | "dialogFull";

const SIZES: Record<ModalSize, string> = {
  dialog: "max-w-dialog",
  dialogWide: "max-w-dialogWide",
  dialogFull: "max-w-dialogFull",
};

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  size?: ModalSize;
  footer?: ReactNode;
  children?: ReactNode;
  /**
   * Set false for a dialog that must not be dismissed by clicking the scrim —
   * a destructive confirmation where an accidental click outside should not
   * read as an answer.
   */
  dismissOnScrim?: boolean;
  /**
   * `alertdialog` for a dialog that interrupts and demands an answer — a
   * destructive confirmation. Screen readers announce the two differently, and
   * a confirm that only says "dialog" is read as optional.
   */
  role?: "dialog" | "alertdialog";
  /** id of an element inside `children` that carries the description. */
  describedBy?: string;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  size = "dialog",
  footer,
  children,
  dismissOnScrim = true,
  role = "dialog",
  describedBy,
  className,
}: ModalProps) {
  const { t } = useTranslation("common");
  const panelRef = useRef<HTMLDivElement>(null);
  // Hooks run before the `!open` return below — an id generated after it would
  // change the hook count between renders.
  const titleId = useId();

  // Focus in on open, Tab held inside, Escape out, focus back on the trigger.
  useFocusTrap(panelRef, open, onClose);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-overlay flex items-center justify-center bg-overlay p-wide"
      onMouseDown={(event) => {
        if (dismissOnScrim && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={[
          "z-modal flex max-h-full w-full flex-col overflow-hidden",
          "rounded-sheet border border-line bg-card shadow-overlay outline-none",
          SIZES[size],
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <header className="flex shrink-0 items-start gap-soft border-b border-line px-roomy py-soft">
          <h2 id={titleId} className="min-w-0 flex-1 text-title text-ink-primary">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("modal.close")}
            onClick={onClose}
            className="shrink-0 rounded-tile p-tight text-ink-muted hover:bg-white/10 hover:text-ink-primary"
          >
            <X size={16} aria-hidden />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-roomy py-soft">
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