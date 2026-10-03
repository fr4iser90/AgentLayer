import { forwardRef, type InputHTMLAttributes } from "react";

/**
 * The radio, drawn for the same reason as `Checkbox`: five of the six in the
 * tree carried no class at all, so they rendered as the UA's light-mode control
 * in a dark form — and the sixth sized its own 16 px box with a 2 px violet ring
 * for one review column. That one stays as it is: its hue groups the block it
 * belongs to, and a caller class of the same specificity as the ones below is
 * settled by stylesheet order, not by intent.
 *
 * Unlike the checkbox, a radio cannot show its state with a glyph inside the
 * box: the filled dot is what distinguishes "this one of the set". It is drawn
 * the same way — a pseudo-element, `ink-on-fill` on the accent fill, the pair
 * `Button` measured — so the two box controls take their hue from one place.
 */
const BOX = [
  "relative shrink-0 cursor-pointer appearance-none rounded-pill",
  "h-4 w-4 border border-line bg-field",
  "transition-colors duration-fast ease-standard",
  "focus-visible:outline-hidden focus-visible:shadow-focus",
  "disabled:cursor-not-allowed disabled:opacity-45",
  "checked:border-accent checked:bg-accent",
].join(" ");

const DOT = [
  "after:absolute after:left-1/2 after:top-1/2 after:content-['']",
  "after:h-2 after:w-2 after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-pill",
  "after:bg-ink-on-fill after:opacity-0 checked:after:opacity-100",
].join(" ");

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { className, ...rest },
  ref
) {
  return (
    <input
      ref={ref}
      type="radio"
      className={[BOX, DOT, className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
});