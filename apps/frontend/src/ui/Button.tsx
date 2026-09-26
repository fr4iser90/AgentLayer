import { forwardRef, type ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";
/**
 * Fill hue for `variant="primary"`. The app already had filled buttons in all
 * four hues — success on save, warning on revoke, danger on confirm dialogs —
 * each carrying its own fill-and-ink pair at the call site, which is how the
 * same green button was the success token with white ink in one file and a raw
 * palette green with black ink in another. The hue is the primitive's decision
 * now, and so is the ink on it: `ink-on-fill` is the near-black that passes on
 * every saturated fill, where white reaches only 2.52-3.35:1.
 */
export type ButtonTone = "accent" | "success" | "warning" | "danger";

const BASE = [
  "inline-flex select-none items-center justify-center gap-base whitespace-nowrap rounded-card font-medium",
  "transition-colors duration-fast ease-standard",
  "focus-visible:outline-none focus-visible:shadow-focus",
  "disabled:pointer-events-none disabled:opacity-45",
].join(" ");

const VARIANTS: Record<ButtonVariant, string> = {
  // Dark ink on the fill: white fails on every saturated fill in this palette
  // (2.52-3.35:1), including the sky-600 primary it replaces at 4.10:1.
  primary: "bg-accent text-ink-on-fill hover:bg-accent-hover active:bg-accent-press",
  secondary:
    "border border-line bg-transparent text-ink-primary hover:border-line-strong hover:bg-white/5 active:bg-white/10",
  ghost: "text-ink-secondary hover:bg-white/5 hover:text-ink-primary active:bg-white/10",
  // Outlined by default. A filled destructive belongs in a confirm dialog, not
  // on every row — the app used to read as "everything red".
  danger:
    "border border-danger/45 bg-transparent text-badge-danger hover:border-danger hover:bg-danger-subtle active:bg-danger/25",
};

/** Filled surface per hue. Only `variant="primary"` reads from this table. */
const TONES: Record<ButtonTone, string> = {
  accent: "bg-accent text-ink-on-fill hover:bg-accent-hover active:bg-accent-press",
  success: "bg-success text-ink-on-fill hover:bg-success-hover active:bg-success/80",
  warning: "bg-warning text-ink-on-fill hover:bg-warning-hover active:bg-warning/80",
  danger: "bg-danger text-ink-on-fill hover:bg-danger-hover active:bg-danger/80",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-firm text-label",
  md: "h-8 px-soft text-body",
  lg: "h-9 px-wide text-body",
};

/**
 * Icon-only buttons: as wide as they are tall, no horizontal padding. These
 * were sized per file as `h-6 w-6 p-0`, `h-7 w-7 p-1` and plain `p-2`, so the
 * same icon control had four hit areas across the app.
 */
const SQUARES: Record<ButtonSize, string> = {
  sm: "h-7 w-7 p-0 text-label",
  md: "h-8 w-8 p-0 text-body",
  lg: "h-9 w-9 p-0 text-body",
};

export function buttonClass(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  extra?: string,
  tone: ButtonTone = "accent",
  square = false
): string {
  const surface = variant === "primary" ? TONES[tone] : VARIANTS[variant];
  return [BASE, surface, square ? SQUARES[size] : SIZES[size], extra]
    .filter(Boolean)
    .join(" ");
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Fill hue; only meaningful with `variant="primary"`. */
  tone?: ButtonTone;
  /** Icon-only button: square, no horizontal padding. */
  square?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    tone = "accent",
    square = false,
    type = "button",
    className,
    ...rest
  },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass(variant, size, className, tone, square)}
      {...rest}
    />
  );
});
