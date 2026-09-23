import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

/**
 * `disabled` and `readOnly` mean different things and must not look the same.
 *
 *   disabled — the control is not available. Dimmed, not-allowed cursor, out of
 *              the tab order (native).
 *   readOnly — the value is content. It stays full contrast, stays selectable so
 *              it can be copied, and drops the field chrome so it does not
 *              advertise an edit affordance it will not honour.
 *
 * Before this, read-only inputs kept the editable field border and were
 * indistinguishable from editable ones.
 */
const FIELD_BASE = [
  "w-full rounded-card border border-line bg-field px-soft py-snug text-body text-ink-primary",
  "placeholder:text-field-placeholder",
  "transition-colors duration-fast ease-standard",
  "focus:border-line-focus focus:outline-none focus:shadow-focus",
  "disabled:cursor-not-allowed disabled:opacity-45",
  "read-only:cursor-default read-only:border-transparent read-only:bg-transparent",
].join(" ");

const FIELD_MONO = "font-mono";

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  function TextInput({ mono = false, className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={[FIELD_BASE, mono && FIELD_MONO, className]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      />
    );
  }
);

export interface TextAreaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  mono?: boolean;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea({ mono = false, className, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        className={[FIELD_BASE, mono && FIELD_MONO, className]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      />
    );
  }
);

export interface SelectProps
  extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, children, ...rest },
  ref
) {
  return (
    <select
      ref={ref}
      className={[FIELD_BASE, "cursor-pointer pr-deep", className]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </select>
  );
});

export { FIELD_BASE as fieldClass };
