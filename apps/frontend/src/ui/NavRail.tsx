import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { NavSurface } from "../layout/navModel";

const leaf =
  "flex items-center gap-snug rounded-card border border-transparent px-soft py-base text-sm transition-colors";
const leafActive = "border-line bg-white/10 text-ink-primary";
const leafIdle = "text-ink-muted hover:bg-white/5 hover:text-ink-secondary";

/**
 * The one nav container.
 *
 * It is rendered twice by `AppShell` — statically in the column on `md+`, and
 * inside a drawer below that — which is why it takes no layout of its own and
 * no knowledge of whether it is open. There is exactly one list of links, so
 * the mobile rail cannot drift from the desktop one, and there is exactly one
 * drawer mechanism in the app.
 */
export function NavRail({ surface }: { surface: NavSurface }) {
  const { t } = useTranslation([surface.namespace, "common"]);
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
            {section.leaves.map((item) => {
              const label = t(item.labelKey, { ns: surface.namespace });
              const Icon = item.icon;
              if (item.external) {
                return (
                  <a
                    key={item.to}
                    href={item.to}
                    target="_blank"
                    rel="noreferrer"
                    className={`${leaf} ${leafIdle}`}
                  >
                    <Icon size={16} aria-hidden className="shrink-0" />
                    <span className="truncate">{label}</span>
                  </a>
                );
              }
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `${leaf} ${isActive ? leafActive : leafIdle}`}
                >
                  <Icon size={16} aria-hidden className="shrink-0" />
                  <span className="truncate">{label}</span>
                </NavLink>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}