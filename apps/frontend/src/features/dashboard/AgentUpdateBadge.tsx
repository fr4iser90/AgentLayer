/** Unread agent-update indicator for dashboard blocks. */
export function AgentUpdateBadge(props: {
  title?: string;
  /** corner = floating top-right on block; inline = compact in toolbars */
  variant?: "corner" | "inline";
  pulse?: boolean;
}) {
  const { title, variant = "corner", pulse = false } = props;
  const label = title ?? "Agent update";

  if (variant === "inline") {
    return (
      <span
        className={[
          "inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-orange-500 px-1 text-[9px] font-bold leading-none text-black shadow",
          pulse ? "animate-pulse" : "",
        ].join(" ")}
        title={label}
        aria-label={label}
      >
        !
      </span>
    );
  }

  return (
    <span
      className={[
        "pointer-events-none absolute right-2 top-2 z-20 flex h-5 min-w-5 items-center justify-center rounded-full bg-orange-500 px-1 text-[10px] font-bold leading-none text-black shadow-lg ring-2 ring-black/40",
        pulse ? "animate-pulse" : "",
      ].join(" ")}
      title={label}
      aria-label={label}
    >
      !
    </span>
  );
}
