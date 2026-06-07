import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

const MIN_HEIGHT_PX = 52;
const MAX_HEIGHT_VH = 0.4;
const MAX_HEIGHT_CAP_PX = 360;

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  disabled?: boolean;
  onEnterSend?: () => void;
  onEnterForceSend?: () => void;
  canForceSend?: boolean;
};

export const ChatComposerTextarea = forwardRef<HTMLTextAreaElement, Props>(function ChatComposerTextarea(
  {
    value,
    onChange,
    placeholder,
    disabled,
    onEnterSend,
    onEnterForceSend,
    canForceSend,
  },
  forwardedRef
) {
  const innerRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(forwardedRef, () => innerRef.current as HTMLTextAreaElement);

  useEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = Math.min(
      typeof window !== "undefined" ? window.innerHeight * MAX_HEIGHT_VH : MAX_HEIGHT_CAP_PX,
      MAX_HEIGHT_CAP_PX
    );
    const next = Math.max(MIN_HEIGHT_PX, Math.min(el.scrollHeight, max));
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }, [value]);

  return (
    <textarea
      ref={innerRef}
      disabled={disabled}
      className="min-h-[52px] w-full resize-none bg-transparent text-sm leading-relaxed text-neutral-100 placeholder:text-neutral-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      rows={2}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (disabled) return;
          if (canForceSend && (e.metaKey || e.ctrlKey)) {
            onEnterForceSend?.();
          } else {
            onEnterSend?.();
          }
        }
      }}
    />
  );
});
