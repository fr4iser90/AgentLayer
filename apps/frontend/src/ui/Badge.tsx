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

/**
 * The chip recipe without the element.
 *
 * A badge is a colour decision, not a `<span>`. A large share of the chips in
 * this app are interactive — `<summary>` disclosures, `<Link>` status pills,
 * `<button>` filters — and a span-only primitive leaves those hand-rolling the
 * same fill+text pair forever, which is the drift this primitive exists to stop.
 * Callers that must own their tag take the classes and keep the element.
 */
export function badgeClasses(
  tone: BadgeTone,
  ...extra: Array<string | false | null | undefined>
): string {
  return [BASE, TONES[tone], ...extra].filter(Boolean).join(" ");
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  children?: ReactNode;
}

export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span className={badgeClasses(tone, className)} {...rest}>
      {children}
    </span>
  );
}
