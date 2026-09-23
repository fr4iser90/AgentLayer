import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { canManageWorkspaceGrants } from "../pages/admin/accessGating";

const item =
  "block rounded-card border border-transparent px-3 py-2 text-sm transition-colors";
const itemActive = "border-line bg-white/10 text-ink-primary";
const itemIdle = "text-ink-muted hover:bg-white/5 hover:text-neutral-200";

function NavGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-4 first:mt-0">
      <p className="mb-1 px-2 text-meta font-medium uppercase tracking-wide text-ink-muted/90">
        {label}
      </p>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

/** Tenant-scoped day-2 admin — separate from platform operator `/admin`. */
export function OrgAdminLayout() {
  const { t } = useTranslation(["org"]);
  const { user } = useAuth();
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-canvas md:flex-row">
      <aside className="shrink-0 border-b border-line bg-panel px-3 py-4 md:w-56 md:border-b-0 md:border-r">
        <p className="mb-1 px-2 text-meta font-medium uppercase tracking-wide text-ink-muted">
          {t("org:sidebarTitle")}
        </p>
        <nav className="flex flex-col" aria-label={t("org:sidebarAria")}>
          <NavGroup label={t("org:navKnowledge")}>
            <NavLink
              to="/org/knowledge"
              className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
            >
              {t("org:navKnowledge")}
            </NavLink>
          </NavGroup>
          <NavGroup label={t("org:navTeam")}>
            <NavLink
              to="/org/team"
              className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
            >
              {t("org:navTeam")}
            </NavLink>
          </NavGroup>
          {canManageWorkspaceGrants(user) ? (
            <NavGroup label={t("org:navSharing")}>
              <NavLink
                to="/org/grants"
                className={({ isActive }) => `${item} ${isActive ? itemActive : itemIdle}`}
              >
                {t("org:navGrants")}
              </NavLink>
            </NavGroup>
          ) : null}
        </nav>
        <NavLink
          to="/"
          className="mt-6 block px-3 py-2 text-xs text-sky-400/90 hover:text-sky-300 hover:underline"
        >
          {t("org:backToApp")}
        </NavLink>
      </aside>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <Outlet />
      </div>
    </div>
  );
}
