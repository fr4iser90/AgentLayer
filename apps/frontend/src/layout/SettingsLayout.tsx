import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

const subLink =
  "block rounded-lg px-3 py-2 text-sm transition-colors border border-transparent";

const subLinkActive = "bg-white/10 text-white border-white/10";
const subLinkIdle = "text-surface-muted hover:bg-white/5 hover:text-neutral-200";

export function SettingsLayout() {
  const { t } = useTranslation(["settings", "common"]);
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden md:flex-row">
      <aside className="shrink-0 border-b border-surface-border bg-[#111] px-3 py-4 md:w-52 md:border-b-0 md:border-r">
        <p className="mb-3 px-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
          {t("common:settings")}
        </p>
        <nav
          className="flex flex-row flex-wrap gap-1 md:flex-col md:gap-0.5"
          aria-label={t("settings:settingsSectionsAria")}
        >
          <NavLink
            to="/settings/profile"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:profileTitle")}
          </NavLink>
          <NavLink
            to="/settings/connections"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:connectionsTitle")}
          </NavLink>
          <NavLink
            to="/settings/tools"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:toolsTitle")}
          </NavLink>
          <NavLink
            to="/settings/agent"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:agentTitle")}
          </NavLink>
          <NavLink
            to="/settings/friends"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            👥 {t("settings:friendsTitle")}
          </NavLink>
          <NavLink
            to="/settings/shares"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            🔗 {t("settings:sharesTitle")}
          </NavLink>
        </nav>
      </aside>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
        <Outlet />
      </div>
    </div>
  );
}
