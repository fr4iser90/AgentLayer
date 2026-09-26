import { forwardRef, type ButtonHTMLAttributes } from "react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  /**
   * No colour layer of its own. The surfaces migrated in this pass — nav rows,
   * accordion headers, clickable cards — already carry their background, border
   * and hover state, and every one of them also wanted the base (focus ring,
   * disabled, `type="button"`), which is what made them buttons.
   *
   * Feeding those through `ghost` or `secondary` instead would put a second
   * fill and hairline on the same element as the surface's own, and Tailwind
   * resolves that by generated order rather than by intent. Only meaningful
   * together with `block`; the control-primitives guard rejects
   * `variant="plain"` without it, so it cannot become a licence to hand-draw a
   * normal button.
   */
  | "plain";
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
  "inline-flex select-none font-medium",
  "transition-colors duration-fast ease-standard",
  "focus-visible:outline-none focus-visible:shadow-focus",
  "disabled:pointer-events-none disabled:opacity-45",
].join(" ");

/**
 * The box every ordinary control shares. `plain` releases it — a nav row wants
 * `rounded-tile`, a clickable card wants `rounded-sheet`, and the primitive
 * cannot know which, while the call site always can.
 */
const RADIUS = "rounded-card";

/**
 * The content box of a control: hugs the label, centres it, keeps it on one
 * line, spaces icon from text.
 */
const CONTROL = "items-center justify-center gap-base whitespace-nowrap";

/**
 * A button that fills its container instead of hugging its label — accordion
 * headers, clickable cards, nav rows. Twenty-eight of these carried their own
 * `justify-between`, `flex-col`, `min-h-[…]` or `text-left` at the call site.
 *
 * Those properties cannot simply be appended to `CONTROL`: when two utilities
 * set the same CSS property, Tailwind's generated order decides the winner, not
 * the order in the class attribute — the call site would look right and render
 * centred, fixed-height and clipped. `block` therefore *releases* the axis
 * alignment, the gap, the padding and the height, and asserts only the text
 * alignment a native `<button>` cannot get on its own (its default is centred).
 */
const BLOCK = "text-left";

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
  // See the note on `ButtonVariant`. Empty by design: the surface is the colour.
  plain: "",
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
  square = false,
  block = false
): string {
  const surface = variant === "primary" ? TONES[tone] : VARIANTS[variant];
  // `plain` is the base and nothing else — no colour, no radius, no size box.
  // A surface that already has all three still needs the focus ring, the
  // disabled state and `type="button"`, and it needs the properties it owns to
  // stay uncontested.
  if (variant === "plain")
    return [BASE, block ? BLOCK : undefined, extra].filter(Boolean).join(" ");
  return [
    BASE,
    RADIUS,
    block ? BLOCK : CONTROL,
    surface,
    // A `block` surface has no height of its own: the content and the call
    // site's padding decide it. Emitting `h-8` here would fight `min-h-[…]`
    // and `h-full` on those surfaces.
    block ? undefined : square ? SQUARES[size] : SIZES[size],
    extra,
  ]
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
  /** Full-width surface — see `BLOCK`. */
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    tone = "accent",
    square = false,
    block = false,
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
      className={buttonClass(variant, size, className, tone, square, block)}
      {...rest}
    />
  );
});
