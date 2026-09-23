import type { HTMLAttributes, ReactNode } from "react";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger";

const BASE =
  "inline-flex select-none items-center gap-tight rounded-pill px-base py-hair text-label font-medium whitespace-nowrap";

const TONES: Record<BadgeTone, string> = {
  // /8 is not in Tailwind's opacity scale and silently generates nothing; /10 is.
  neutral: "bg-white/10 text-ink-secondary",
  accent: "bg-accent-subtle text-badge-accent",
  success: "bg-success-subtle text-badge-success",
  warning: "bg-warning-subtle text-badge-warning",
  danger: "bg-danger-subtle text-badge-danger",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  children?: ReactNode;
}

export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={[BASE, TONES[tone], className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </span>
  );
}
