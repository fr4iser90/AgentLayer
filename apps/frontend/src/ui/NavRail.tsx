import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import type { NavLeaf, NavSurface } from "../layout/navModel";

const leaf =
  "flex items-center gap-snug rounded-card border border-transparent px-base py-base text-sm transition-colors";
const leafActive = "border-line bg-white/10 text-ink-primary";
const leafIdle = "text-ink-muted hover:bg-white/5 hover:text-ink-secondary";
const fold =
  "shrink-0 self-stretch rounded-tile px-tight text-ink-muted hover:bg-white/5 hover:text-ink-primary";

/**
 * The one nav container.
 *
 * It is rendered twice by `AppShell` — statically in the column on `md+`, and
 * inside a drawer below that — which is why it takes no layout of its own and
 * no knowledge of whether it is open. There is exactly one list of links, so the
 * mobile rail cannot drift from the desktop one, and there is exactly one drawer
 * mechanism in the app.
 *
 * The one thing that differs between the two renderings is which door the reader
 * folded, so that is the one piece of state `AppShell` holds for the rail and
 * hands back to both. A fold has no value until somebody asks for one, and the
 * default is open while the route is below the door — the list never hides the
 * page you are on by itself. A collapse the reader pressed is honoured even then,
 * because the door row above the closed group stays lit (a `NavLink` without
 * `end` matches its descendants), so where you are stays named.
 */
export function NavRail({
  surface,
  folds,
  onFold
}: {
  surface: NavSurface;
  folds: Record<string, boolean>;
  onFold: (to: string, open: boolean) => void;
}) {
  const { t } = useTranslation([surface.namespace, "common"]);
  const { pathname } = useLocation();
  return (
    <nav className="flex flex-col" aria-label={t(surface.ariaKey, { ns: surface.namespace })}>
      {surface.sections.map((section, i) => (
        <div key={section.labelKey ?? `ungrouped-${i}`} className="mt-wide first:mt-0">
          {section.labelKey ? (
            <p className="mb-tight px-base text-meta font-medium uppercase tracking-wide text-ink-muted">
              {t(section.labelKey, { ns: surface.namespace })}
            </p>
          ) : null}
          <div className="flex flex-col gap-hair">
            {section.leaves.map((item) =>
              renderLeaf(item, t, surface.namespace, folds, onFold, pathname)
            )}
          </div>
        </div>
      ))}
    </nav>
  );
}

type Translate = (key: string, options: Record<string, unknown>) => string;

function renderLeaf(
  item: NavLeaf,
  t: Translate,
  ns: string,
  folds: Record<string, boolean>,
  onFold: (to: string, open: boolean) => void,
  pathname: string
) {
  const label = t(item.labelKey, { ns });
  const Icon = item.icon;
  const row = item.external ? (
    <a href={item.to} target="_blank" rel="noreferrer" className={`${leaf} ${leafIdle} min-w-0`}>
      <Icon size={16} aria-hidden className="shrink-0" />
      <span className="truncate">{label}</span>
    </a>
  ) : (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => `${leaf} min-w-0 ${isActive ? leafActive : leafIdle}`}
    >
      <Icon size={16} aria-hidden className="shrink-0" />
      <span className="truncate">{label}</span>
    </NavLink>
  );

  const pages = item.children ?? [];
  if (!pages.length) return <div key={item.to}>{row}</div>;

  const open = folds[item.to] ?? isBelow(pathname, item.to);
  const listId = `nav-group-${item.to.replace(/[^a-z0-9]/gi, "-")}`;
  return (
    <div key={item.to}>
      <div className="flex items-stretch gap-hair">
        {row}
        <button
          type="button"
          className={fold}
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-label={t(open ? "nav.collapseGroup" : "nav.expandGroup", {
            ns: "common",
            group: label
          })}
          onClick={() => onFold(item.to, !open)}
        >
          <ChevronRight
            size={14}
            aria-hidden
            className={`block transition-transform ${open ? "rotate-90" : ""}`}
          />
        </button>
      </div>
      {open ? (
        <div id={listId} className="ml-wide mt-hair flex flex-col gap-hair border-l border-line pl-hair">
          {pages.map((child) => (
            <NavLink
              key={child.to}
              to={child.to}
              end={child.end}
              className={({ isActive }) => `${leaf} ${isActive ? leafActive : leafIdle}`}
            >
              <child.icon size={16} aria-hidden className="shrink-0" />
              <span className="truncate">{t(child.labelKey, { ns })}</span>
            </NavLink>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Is `pathname` this path or below it? A door is not a prefix of a longer name. */
function isBelow(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}