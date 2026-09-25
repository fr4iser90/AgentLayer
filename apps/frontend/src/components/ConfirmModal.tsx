import { useId } from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";

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

/**
 * Destructive confirmation.
 *
 * It keeps its own `alertdialog` role rather than being a plain dialog: the
 * point of this box is that the answer is not optional. Everything else —
 * focus trap, Escape, scroll lock, focus restore — comes from `Modal`, which
 * this file did not have before. It handled Escape itself and let Tab walk out
 * of the box into the page behind it.
 */
export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = "default",
  busy = false,
  onConfirm,
  onCancel
}: Props) {
  const descId = useId();
  // While the action is in flight the box must not be dismissible: closing it
  // would read as an answer the user never gave, and there is no undo.
  const requestClose = () => {
    if (!busy) onCancel();
  };

  return (
    <Modal
      open={open}
      onClose={requestClose}
      title={title}
      role="alertdialog"
      describedBy={descId}
      dismissOnScrim={!busy}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "…" : confirmLabel}
          </Button>
        </>
      }
    >
      <p id={descId} className="text-body leading-relaxed text-ink-secondary">
        {description}
      </p>
    </Modal>
  );
}