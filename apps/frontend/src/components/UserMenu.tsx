import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { Mascot, pickCharacter } from "../ui/Mascot";
import { Menu } from "../ui/Menu";
import { Tooltip } from "../ui/Tooltip";
import { useClickOutside } from "../ui/useClickOutside";
import { Button } from "../ui/Button";

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
      <Button
        variant="ghost"
        size="lg"
          type="button"
          className="h-9 w-9 outline-none ring-accent/40 hover:scale-105"
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={() => setOpen((v) => !v)}
      >
          <Mascot character={pickCharacter(email)} state={open ? "happy" : "idle"} size={30} ariaLabel={null} />
        </Button>
      </Tooltip>
      {open ? (
        <Menu
          onClose={() => setOpen(false)}
          header={
            email ? (
              <p
                className="truncate border-b border-line px-soft py-base text-label text-ink-muted"
                title={email}
              >
                {email}
              </p>
            ) : null
          }
          items={[
            {
              id: "sign-out",
              label: t("userMenu.signOut"),
              tone: "danger",
              onSelect: () => void logout(),
            },
          ]}
        />
      ) : null}
    </div>
  );
}
