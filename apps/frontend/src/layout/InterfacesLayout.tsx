import { NavLink, Outlet } from "react-router-dom";
import { OperatorSettingsProvider } from "../features/admin/operatorSettings/OperatorSettingsProvider";
import { OperatorSettingsStickySave } from "../features/admin/operatorSettings/OperatorSettingsStickySave";

const subLink =
  "block rounded-lg border border-transparent px-3 py-2 text-sm transition-colors";
const subActive = "border-white/10 bg-white/10 text-white";
const subIdle = "text-surface-muted hover:bg-white/5 hover:text-neutral-200";

const NAV = [
  { to: "/admin/interfaces", end: true, label: "Overview" },
  { to: "/admin/interfaces/bridges", label: "Bridges" },
  { to: "/admin/interfaces/llm", label: "LLM & routing" },
  { to: "/admin/interfaces/memory", label: "Memory & RAG" },
  { to: "/admin/interfaces/automation", label: "Automation" },
  { to: "/admin/interfaces/platform", label: "Platform" },
] as const;

export function InterfacesLayout() {
  return (
    <OperatorSettingsProvider>
      <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <aside className="shrink-0 border-b border-surface-border bg-[#0a0a0a] px-3 py-4 md:w-48 md:border-b-0 md:border-r">
          <p className="mb-2 px-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
            Interfaces
          </p>
          <nav className="flex flex-row flex-wrap gap-1 md:flex-col md:gap-0.5" aria-label="Interface settings">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={"end" in item ? item.end : false}
                className={({ isActive }) => `${subLink} ${isActive ? subActive : subIdle}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
          <Outlet />
          <OperatorSettingsStickySave />
        </div>
      </div>
    </OperatorSettingsProvider>
  );
}
