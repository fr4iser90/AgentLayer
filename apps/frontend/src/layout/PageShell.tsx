import type { ReactNode } from "react";

/**
 * The one content-width shell for routed pages.
 *
 * AppShell owns chrome (header + rail). PageShell owns the reading/work column:
 * pages must not invent their own `mx-auto max-w-page*`. Pick a density; the
 * page-shell lint enforces which densities are allowed per surface.
 */
export type PageShellDensity = "narrow" | "default" | "wide" | "measure" | "dialog" | "fill";

const DENSITY_MAX: Record<Exclude<PageShellDensity, "fill">, string> = {
  narrow: "max-w-pageNarrow",
  default: "max-w-page",
  wide: "max-w-pageWide",
  measure: "max-w-measure",
  dialog: "max-w-dialog",
};

export function PageShell({
  density = "default",
  padded = true,
  className = "",
  children,
}: {
  density?: PageShellDensity;
  /** When false, only the max-width column is applied (nested shells inside padded parents). */
  padded?: boolean;
  className?: string;
  children: ReactNode;
}) {
  if (density === "fill") {
    return (
      <div className={["flex h-full min-h-0 w-full min-w-0 flex-col", className].filter(Boolean).join(" ")}>
        {children}
      </div>
    );
  }
  const pad =
    density === "dialog"
      ? "px-broad py-grand"
      : padded
        ? "px-broad py-deep"
        : "";
  return (
    <div
      className={["mx-auto w-full", DENSITY_MAX[density], pad, className].filter(Boolean).join(" ")}
    >
      {children}
    </div>
  );
}
