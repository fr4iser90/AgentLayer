import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { hasOrgSurface } from "../auth/deploymentMode";
import { Mascot, pickCharacter } from "../ui/Mascot";
import { Tooltip } from "../ui/Tooltip";

export function UserMenu() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const email = user?.email ?? "";
  const siteAdmin =
    user?.site_role === "site_admin" || user?.role?.toLowerCase() === "admin";
  const showOrg =
    hasOrgSurface(user) &&
    (user?.membership_role === "tenant_owner" || user?.membership_role === "tenant_admin");

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <Tooltip label={email || t("userMenu.account")}>
      <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-pill outline-none ring-sky-500/40 transition-transform duration-fast ease-standard hover:scale-105 focus-visible:ring-2"
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={() => setOpen((v) => !v)}
        >
          <Mascot character={pickCharacter(email)} state={open ? "happy" : "idle"} size={30} ariaLabel={null} />
        </button>
      </Tooltip>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-menu mt-tight min-w-[12rem] rounded-card border border-line bg-[#1a1a1a] py-tight shadow-xl"
        >
          {email ? (
            <p className="truncate border-b border-line px-soft py-base text-xs text-ink-muted" title={email}>
              {email}
            </p>
          ) : null}
          <Link
            role="menuitem"
            to="/settings"
            className="block px-soft py-base text-sm text-ink-primary hover:bg-white/10"
            onClick={() => setOpen(false)}
          >
            {t("userMenu.settings")}
          </Link>
          {showOrg ? (
            <Link
              role="menuitem"
              to="/org"
              className="block px-soft py-base text-sm text-ink-primary hover:bg-white/10"
              onClick={() => setOpen(false)}
            >
              {t("userMenu.organization")}
            </Link>
          ) : null}
          {siteAdmin ? (
            <Link
              role="menuitem"
              to="/admin"
              className="block px-soft py-base text-sm text-ink-primary hover:bg-white/10"
              onClick={() => setOpen(false)}
            >
              {t("userMenu.platformAdmin")}
            </Link>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="w-full px-soft py-base text-left text-sm text-ink-muted hover:bg-white/10 hover:text-neutral-200"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            {t("userMenu.signOut")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
