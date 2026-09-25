import { forwardRef, type ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

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

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-firm text-label",
  md: "h-8 px-soft text-body",
  lg: "h-9 px-wide text-body",
};

export function buttonClass(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  extra?: string
): string {
  return [BASE, VARIANTS[variant], SIZES[size], extra].filter(Boolean).join(" ");
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", type = "button", className, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass(variant, size, className)}
      {...rest}
    />
  );
});
