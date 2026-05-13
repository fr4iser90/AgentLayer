import { NavLink, Outlet } from "react-router-dom";

/** Single canonical admin sidebar — do not nest extra IDE submenus here. */
const item =
  "block rounded-lg border border-transparent px-3 py-2 text-sm transition-colors";
const itemActive = "border-white/10 bg-white/10 text-white";
const itemIdle = "text-surface-muted hover:bg-white/5 hover:text-neutral-200";

export function AdminLayout() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-surface md:flex-row">
      <aside className="shrink-0 border-b border-surface-border bg-[#111] px-3 py-4 md:w-52 md:border-b-0 md:border-r">
        <p className="mb-1 px-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
          Operator admin
        </p>
        <nav className="flex flex-col gap-0.5" aria-label="Admin sections">
          <NavLink
            to="/admin"
            end
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Overview
          </NavLink>
          <NavLink
            to="/admin/interfaces"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Interfaces
          </NavLink>
          <NavLink
            to="/admin/ide-integration"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            IDE integration
          </NavLink>
          <NavLink
            to="/admin/tools"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Tools
          </NavLink>
          <NavLink
            to="/admin/users"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Users
          </NavLink>
          <NavLink
            to="/admin/scheduled-jobs"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Scheduled jobs
          </NavLink>
          <NavLink
            to="/admin/schedules"
            className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
          >
            Schedules
          </NavLink>
        </nav>
        <NavLink
          to="/"
          className="mt-6 block px-3 py-2 text-xs text-sky-400/90 hover:text-sky-300 hover:underline"
        >
          ← Back to app
        </NavLink>
      </aside>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <Outlet />
      </div>
    </div>
  );
}
