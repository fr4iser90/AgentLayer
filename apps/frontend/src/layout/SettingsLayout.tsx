import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Link, Users } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { friendSystemEnabled } from "../auth/tenantSurface";

const subLinkBase =
  "rounded-lg px-3 py-2 text-sm transition-colors border border-transparent";
const subLink = `${subLinkBase} block`;
const subLinkIcon = `${subLinkBase} flex items-center gap-1.5`;

const subLinkActive = "bg-white/10 text-ink-primary border-line";
const subLinkIdle = "text-ink-muted hover:bg-white/5 hover:text-neutral-200";

export function SettingsLayout() {
  const { t } = useTranslation(["settings", "common"]);
  const { user } = useAuth();
  const friendsOn = friendSystemEnabled(user);
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden md:flex-row">
      <aside className="shrink-0 border-b border-line bg-panel px-3 py-4 md:w-52 md:border-b-0 md:border-r">
        <p className="mb-3 px-2 text-meta font-medium uppercase tracking-wide text-ink-muted">
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
            to="/settings/voice"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:voiceTitle")}
          </NavLink>
          <NavLink
            to="/settings/connections"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:connectionsTitle")}
          </NavLink>
          <NavLink
            to="/settings/notifications"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:notificationsTitle")}
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
            to="/settings/delegate"
            className={({ isActive }) => `${subLink} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            {t("settings:delegateNav")}
          </NavLink>
          {friendsOn ? (
            <NavLink
              to="/settings/friends"
              className={({ isActive }) => `${subLinkIcon} ${isActive ? subLinkActive : subLinkIdle}`}
            >
              <Users aria-hidden className="h-4 w-4 shrink-0" />
              {t("settings:friendsTitle")}
            </NavLink>
          ) : null}
          <NavLink
            to="/settings/shares"
            className={({ isActive }) => `${subLinkIcon} ${isActive ? subLinkActive : subLinkIdle}`}
          >
            <Link aria-hidden className="h-4 w-4 shrink-0" />
            {t("settings:sharesTitle")}
          </NavLink>
        </nav>
      </aside>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
        <Outlet />
      </div>
    </div>
  );
}
