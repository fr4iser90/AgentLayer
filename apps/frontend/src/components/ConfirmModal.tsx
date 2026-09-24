import { useEffect, useId } from "react";

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  variant?: "danger" | "default";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = "default",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const confirmClass =
    variant === "danger"
      ? "border-red-600/50 bg-red-950/60 text-red-100 hover:bg-red-900/50 disabled:opacity-50"
      : "border-sky-600/50 bg-sky-950/50 text-sky-100 hover:bg-sky-900/40 disabled:opacity-50";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-wide"
      role="presentation"
      onClick={() => {
        if (!busy) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-dialog rounded-sheet border border-line bg-[#1a1a1a] p-roomy shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className="text-base font-semibold text-ink-primary">
          {title}
        </h2>
        <p id={descId} className="mt-base text-sm leading-relaxed text-ink-secondary">
          {description}
        </p>
        <div className="mt-roomy flex flex-wrap justify-end gap-base">
          <button
            type="button"
            className="rounded-card border border-line px-wide py-base text-sm text-ink-primary hover:bg-white/5 disabled:opacity-50"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`rounded-card border px-wide py-base text-sm font-medium ${confirmClass}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
