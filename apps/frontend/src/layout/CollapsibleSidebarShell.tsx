import type { ReactNode } from "react";
import { Drawer } from "../ui/Drawer";

type Props = {
  sidebar: ReactNode;
  children: ReactNode;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  sidebarAriaLabel: string;
  closeSidebarAriaLabel: string;
  /** Tailwind width classes applied from the md breakpoint upward. */
  desktopWidthClass?: string;
  className?: string;
};

/**
 * One region, two shapes: a column from `md` up, a sheet below it.
 *
 * The mobile half used to be its own overlay — a scrim button, a peek-width
 * panel, `md:hidden` — sitting next to `ui/Drawer` as a second drawer
 * mechanism. It had none of what the primitive is for: no dialog role, no
 * Escape, no focus trap, so a keyboard user could Tab out of a panel the app
 * still treated as blocking, and a resize to desktop left the sheet standing
 * over the column that had just reappeared.
 *
 * It is a `Drawer` now: `side="left"` because the column is on the left,
 * `mobileOnly` so the two shapes never exist at once, `flush` because a sidebar
 * list pins its own header and scrolls its own body, `surface="panel"` because
 * the region it replaces is chrome rather than content.
 *
 * What did not survive is the 48px peek gutter, which was the old overlay's one
 * argument for existing: it left the page behind tappable. The close control in
 * the header and the scrim do that on every sheet in the app instead of only
 * here, which is the trade the merge makes.
 */
export function CollapsibleSidebarShell({
  sidebar,
  children,
  mobileOpen,
  onMobileOpenChange,
  sidebarAriaLabel,
  closeSidebarAriaLabel,
  desktopWidthClass = "md:w-[280px]",
  className = "",
}: Props) {
  return (
    <div className={`flex h-full min-h-0 flex-1 overflow-hidden ${className}`.trim()}>
      <aside
        className={[
          "hidden h-full min-h-0 shrink-0 flex-col border-r border-line bg-panel",
          desktopWidthClass,
          "md:flex",
        ].join(" ")}
        aria-label={sidebarAriaLabel}
      >
        {sidebar}
      </aside>

      <Drawer
        open={mobileOpen}
        onClose={() => onMobileOpenChange(false)}
        title={sidebarAriaLabel}
        closeLabel={closeSidebarAriaLabel}
        side="left"
        surface="panel"
        mobileOnly
        flush
      >
        {sidebar}
      </Drawer>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}