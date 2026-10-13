/**
 * The pulsing status dot, which was hand-rolled twice with three nested spans
 * each — once in the chat header chip, once on the voice button — and drifted
 * to two different colours for two different meanings.
 *
 * `active={false}` is not a nicety. A dot in a dense list animates a ping per
 * row; with `active` off it renders the same circle without the ping, which is
 * what a list wants: the state is readable, the movement is not.
 */
export type PulseDotTone = "neutral" | "accent" | "success" | "warning" | "danger";

const PING: Record<PulseDotTone, string> = {
  neutral: "bg-white/40",
  accent: "bg-accent/70",
  success: "bg-success/70",
  warning: "bg-warning/70",
  danger: "bg-danger/70",
};

const CORE: Record<PulseDotTone, string> = {
  neutral: "bg-ink-muted",
  accent: "bg-badge-accent",
  success: "bg-badge-success",
  warning: "bg-badge-warning",
  danger: "bg-badge-danger",
};

export interface PulseDotProps {
  tone?: PulseDotTone;
  /** Off renders a static dot. Required `false` inside lists. */
  active?: boolean;
  /** px. 6 matches the header chip it replaced. */
  size?: number;
  className?: string;
}

export function PulseDot({
  tone = "accent",
  active = true,
  size = 6,
  className,
}: PulseDotProps) {
  const box = { width: size, height: size };
  return (
    <span
      className={["relative inline-flex shrink-0", className].filter(Boolean).join(" ")}
      style={box}
      aria-hidden
    >
      {active ? (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-pill opacity-75 ${PING[tone]}`}
        />
      ) : null}
      <span
        className={`relative inline-flex rounded-pill ${CORE[tone]}`}
        style={box}
      />
    </span>
  );
}