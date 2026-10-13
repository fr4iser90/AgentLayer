/**
 * A card that asks the user to decide something.
 *
 * Five of these existed in chat (secret prompt, secret saved, permission reply,
 * run cards, suggestion cards) and only ONE rendered a `reason` — the other
 * four showed a proposed change with no stated why, which is precisely the
 * information a decision needs. `reason` is therefore a required prop: an
 * action without a reason is a black box with a button on it.
 */
import type { ReactNode } from "react";
import { badgeClasses, type BadgeTone } from "./Badge";

export type ActionCardTone = BadgeTone;

const TONE_EDGE: Record<ActionCardTone, string> = {
  neutral: "border-line",
  accent: "border-accent/45",
  success: "border-success/45",
  warning: "border-warning/50",
  danger: "border-danger/50",
};

export interface ActionCardProps {
  tone?: ActionCardTone;
  title: string;
  /** Why this card exists. Required — see the note above. */
  reason: string;
  primary?: ReactNode;
  secondary?: ReactNode;
  /** Optional short chip next to the title (risk level, source, kind). */
  badge?: { tone?: ActionCardTone; label: string };
  children?: ReactNode;
  className?: string;
}

export function ActionCard({
  tone = "neutral",
  title,
  reason,
  primary,
  secondary,
  badge,
  children,
  className,
}: ActionCardProps) {
  return (
    <section
      className={[
        "rounded-card border bg-card p-soft shadow-card",
        TONE_EDGE[tone],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="flex flex-wrap items-center gap-soft">
        <h3 className="min-w-0 flex-1 text-title text-ink-primary">{title}</h3>
        {badge ? (
          <span className={badgeClasses(badge.tone ?? tone)}>{badge.label}</span>
        ) : null}
      </header>
      <p className="mt-tight text-body text-ink-secondary">{reason}</p>
      {children ? <div className="mt-soft">{children}</div> : null}
      {primary || secondary ? (
        <div className="mt-soft flex flex-wrap items-center gap-base">
          {primary}
          {secondary}
        </div>
      ) : null}
    </section>
  );
}