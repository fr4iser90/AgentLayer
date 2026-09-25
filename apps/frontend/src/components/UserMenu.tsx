import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { Mascot, pickCharacter } from "../ui/Mascot";
import { Tooltip } from "../ui/Tooltip";
import { useClickOutside } from "../ui/useClickOutside";

/**
 * The account control: who you are, in which language, and how to leave.
 *
 * It used to carry links to Settings, the organization and the platform admin.
 * Those were three areas living outside the rail, each with a second copy of the
 * gate that decides them: `siteAdmin` here duplicated `RequireSiteAdmin` line
 * for line, and `showOrg` was a *narrower* rule than `RequireOrgAdmin`, so a
 * content editor who reaches `/org/knowledge` legitimately saw no way in. The
 * rail is the one list of areas — the doors to the other surfaces are leaves of
 * `appNav`, and `check-nav-depth.mjs` fails if a surface loses its door there.
 *
 * What is left is account-level and has no area equivalent.
 */
export function UserMenu() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const email = user?.email ?? "";

  useClickOutside(rootRef, () => setOpen(false), open);

  return (
    <div className="relative" ref={rootRef}>
      <Tooltip label={email || t("userMenu.account")}>
      <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-pill outline-none ring-accent/40 transition-transform duration-fast ease-standard hover:scale-105 focus-visible:ring-2"
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
