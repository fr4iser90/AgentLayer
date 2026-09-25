/**
 * A coloured dot for SYSTEM status — bridge connected, worker running, routing
 * degraded. Deliberately narrow.
 *
 * Agent and conversation state belongs to the mascot, which has 28 poses and is
 * already wired to the turn lifecycle; replacing a face with a dot would be a
 * downgrade. This primitive exists only where there is no face to put: the
 * subsystems whose health nothing in the UI currently says at all.
 *
 * `label` is required. A dot whose colour is the only carrier of meaning is
 * invisible to a screen reader and ambiguous to anyone colourblind.
 */
import { useId } from "react";

export type StatusDotState = "ok" | "degraded" | "down" | "unknown" | "pending";

const DOT: Record<StatusDotState, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  down: "bg-danger",
  unknown: "bg-ink-faint",
  pending: "bg-accent",
};

export interface StatusDotProps {
  state: StatusDotState;
  /** Visible text. The colour is decoration, never the only carrier. */
  label: string;
  /** Hide the text and keep it for assistive tech (dense tables). */
  visuallyLabelOnly?: boolean;
  size?: number;
  className?: string;
}

export function StatusDot({
  state,
  label,
  visuallyLabelOnly = false,
  size = 8,
  className,
}: StatusDotProps) {
  const id = useId();
  return (
    <span className={["inline-flex items-center gap-tight", className].filter(Boolean).join(" ")}>
      <span
        className={`inline-block shrink-0 rounded-pill ${DOT[state]}`}
        style={{ width: size, height: size }}
        aria-hidden
      />
      <span
        id={id}
        className={
          visuallyLabelOnly
            ? "absolute h-px w-px overflow-hidden whitespace-nowrap [clip:rect(0,0,0,0)]"
            : "text-label text-ink-secondary"
        }
      >
        {label}
      </span>
    </span>
  );
}