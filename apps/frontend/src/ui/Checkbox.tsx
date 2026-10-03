import { forwardRef, type InputHTMLAttributes } from "react";

/**
 * The checkbox is drawn here, not by the browser.
 *
 * Eighty of them were spread over the app in three shapes: thirty-six with
 * `className="rounded-tile border-line"` and twenty-four with no class at all —
 * which is not "the dark theme's checkbox" but the UA's light-mode checkbox, a
 * white 13 px square sitting on `bg-canvas` next to text tokens. The rest sized
 * themselves per file (`h-4 w-4`, `h-5 w-5`, `border-2 border-accent/70`).
 *
 * A class alone cannot fix the first group: Tailwind's preflight sets
 * `border-width: 0`, so `border-line` on a control the browser still paints
 * changes a colour that is never drawn. The box only becomes styleable once
 * `appearance: none` hands it over — then every class on it is a class that
 * renders, and the size, the hairline and the fill come from the same tokens as
 * the field next to it.
 *
 * The tick is drawn with the pseudo-element rather than a background image: no
 * data URI in a class list, and its colour is a token, so the ink-on-fill pair
 * `Button` documents (`ink-on-fill` on the saturated fill — white reaches only
 * 2.52-3.35:1) is the same pair here.
 */
const BOX = [
  "relative shrink-0 cursor-pointer appearance-none",
  "border border-line bg-field",
  "transition-colors duration-fast ease-standard",
  "focus-visible:outline-hidden focus-visible:shadow-focus",
  "disabled:cursor-not-allowed disabled:opacity-45",
].join(" ");

/**
 * Elbow of a check: two edges of a small box, turned 45 degrees.
 *
 * `after:content-['']` is not decoration — a pseudo-element without `content`
 * emits no box at all, and the tick would silently be missing while every other
 * class looked correct.
 */
const TICK = [
  "after:absolute after:left-1/2 after:top-1/2 after:content-['']",
  "after:-translate-x-1/2 after:-translate-y-1/2 after:rotate-45",
  "after:border-b-2 after:border-r-2 after:border-ink-on-fill",
  "after:opacity-0 checked:after:opacity-100",
].join(" ");

const TICK_SIZES = { md: "after:h-2 after:w-1", lg: "after:h-2.5 after:w-1.5" } as const;

export type CheckboxSize = keyof typeof TICK_SIZES;

/** The box and its fill, per size. `lg` is the row that needs a bigger target. */
function boxClass(size: CheckboxSize): string {
  const box = size === "lg" ? "h-5 w-5" : "h-4 w-4";
  return [BOX, box, TICK, TICK_SIZES[size], "checked:border-accent checked:bg-accent"].join(" ");
}

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Target size. Both come from the tree: `md` everywhere, `lg` in the benchmark review. */
  size?: CheckboxSize;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { size = "md", className, ...rest },
  ref
) {
  return (
    <input
      ref={ref}
      type="checkbox"
      className={[boxClass(size), className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
});