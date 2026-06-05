import type { ReactNode } from "react";

type Props = {
  sidebar: ReactNode;
  children: ReactNode;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  sidebarAriaLabel: string;
  closeSidebarAriaLabel: string;
  /** Tailwind width classes applied from the md breakpoint upward. */
  desktopWidthClass?: string;
  /** Background for sidebar surfaces (desktop + mobile drawer). */
  sidebarSurfaceClass?: string;
  sidebarClassName?: string;
  className?: string;
};

export function CollapsibleSidebarShell({
  sidebar,
  children,
  mobileOpen,
  onMobileOpenChange,
  sidebarAriaLabel,
  closeSidebarAriaLabel,
  desktopWidthClass = "md:w-[280px]",
  sidebarSurfaceClass = "bg-[#111]",
  sidebarClassName = "",
  className = "",
}: Props) {
  const desktopAsideClass = [
    "hidden h-full min-h-0 shrink-0 flex-col border-r border-surface-border",
    sidebarSurfaceClass,
    desktopWidthClass,
    "md:flex",
    sidebarClassName,
  ]
    .filter(Boolean)
    .join(" ");

  const mobileAsideClass = [
    "relative flex h-full max-h-[100dvh] w-[min(100vw-3rem,280px)] flex-col overflow-hidden border-r border-surface-border shadow-xl",
    sidebarSurfaceClass,
    sidebarClassName,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={`flex h-full min-h-0 flex-1 overflow-hidden ${className}`.trim()}>
      <aside className={desktopAsideClass} aria-label={sidebarAriaLabel}>
        {sidebar}
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 flex md:hidden" role="presentation">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            aria-label={closeSidebarAriaLabel}
            onClick={() => onMobileOpenChange(false)}
          />
          <aside className={mobileAsideClass} aria-label={sidebarAriaLabel}>
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
