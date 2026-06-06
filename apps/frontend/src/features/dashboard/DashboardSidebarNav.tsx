import type { KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { DashboardSummary } from "./types";
import {
  DEFAULT_HUBS,
  type DashboardHub,
  type DashboardHubId,
  type HubGroup,
  hubForSelectedId,
} from "./dashboardHubNav";

const LS_FAV_KEY = "dashboard_nav_favorites_v1";

function loadFavs(): string[] {
  try {
    const raw = localStorage.getItem(LS_FAV_KEY);
    const j = raw ? (JSON.parse(raw) as unknown) : null;
    if (!Array.isArray(j)) return [];
    return j.filter((x) => typeof x === "string");
  } catch {
    return [];
  }
}

function saveFavs(ids: string[]) {
  try {
    localStorage.setItem(LS_FAV_KEY, JSON.stringify(ids.slice(0, 200)));
  } catch {
    // ignore
  }
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function accessNote(role: string | undefined): string {
  if (role === "viewer") return "read-only";
  if (role === "editor") return "shared";
  if (role === "co_owner") return "co-owner";
  return "";
}

function DashboardNavRow(props: {
  w: DashboardSummary;
  selected: boolean;
  active: boolean;
  fav: boolean;
  kindLabel: string;
  unread: number;
  onSelect: () => void;
  onToggleFav: () => void;
  buttonRef?: (el: HTMLButtonElement | null) => void;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { w, selected, active, fav, kindLabel, unread, onSelect, onToggleFav, buttonRef } = props;
  const note = accessNote(w.access_role);

  return (
    <li className="flex items-stretch gap-0.5">
      <button
        ref={buttonRef}
        type="button"
        className={[
          "min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-xs outline-none",
          selected ? "bg-white/10 text-white" : "text-neutral-200",
          active && !selected ? "bg-white/[0.06]" : "",
          !selected && !active ? "hover:bg-white/5" : "",
        ].join(" ")}
        onClick={onSelect}
      >
        <span className="block truncate font-medium leading-snug">
          {w.title || w.kind}
          {unread > 0 ? (
            <span className="ml-1 inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-orange-500 px-0.5 text-[8px] font-bold text-black align-middle">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </span>
        <span className="block truncate text-[10px] leading-snug text-white/35">
          {kindLabel}
          {note ? ` · ${note}` : ""}
        </span>
      </button>
      <button
        type="button"
        title={fav ? t("dashboard:unfavorite") : t("dashboard:favorite")}
        className={[
          "shrink-0 rounded-md px-1.5 text-xs",
          fav ? "text-amber-300/90 hover:bg-amber-950/30" : "text-white/20 hover:bg-white/5 hover:text-white/45",
        ].join(" ")}
        onClick={onToggleFav}
      >
        {fav ? "★" : "☆"}
      </button>
    </li>
  );
}

export function DashboardSidebarNav(props: {
  list: DashboardSummary[];
  grouped: Record<DashboardHubId, HubGroup>;
  hubs?: DashboardHub[];
  selectedId: string | null;
  onSelectDashboard: (id: string) => void;
  kindLabelFor: (kind: string, templateId?: string | null) => string;
  dashboardUnreadCount?: (id: string) => number;
}) {
  const { t } = useTranslation(["dashboard"]);
  const {
    list,
    grouped,
    hubs = DEFAULT_HUBS,
    selectedId,
    onSelectDashboard,
    kindLabelFor,
    dashboardUnreadCount,
  } = props;

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [favIds, setFavIds] = useState<string[]>(() => (typeof window === "undefined" ? [] : loadFavs()));
  const [collapsedHubs, setCollapsedHubs] = useState<Set<DashboardHubId>>(() => new Set());
  const [collapsedInitialized, setCollapsedInitialized] = useState(false);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    saveFavs(favIds);
  }, [favIds]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  const selectedHubId = useMemo(() => hubForSelectedId(grouped, selectedId), [grouped, selectedId]);

  const hubsWithItems = useMemo(
    () => hubs.filter((h) => (grouped[h.id]?.items.length ?? 0) > 0),
    [hubs, grouped]
  );

  useEffect(() => {
    if (collapsedInitialized || hubsWithItems.length <= 1) return;
    setCollapsedHubs(() => {
      const next = new Set(hubsWithItems.map((h) => h.id));
      const expand = selectedHubId ?? hubsWithItems[0]?.id;
      if (expand) next.delete(expand);
      return next;
    });
    setCollapsedInitialized(true);
  }, [collapsedInitialized, hubsWithItems, selectedHubId]);

  useEffect(() => {
    if (!selectedHubId) return;
    setCollapsedHubs((prev) => {
      if (!prev.has(selectedHubId)) return prev;
      const next = new Set(prev);
      next.delete(selectedHubId);
      return next;
    });
  }, [selectedHubId]);

  const showSearch = list.length >= 3;
  const showRecent = list.length > 1 && !query.trim();
  const useFlatList = hubsWithItems.length <= 1;

  const favorites = useMemo(() => {
    const byId = new Map(list.map((w) => [w.id, w]));
    return favIds.map((id) => byId.get(id)).filter((w): w is DashboardSummary => !!w);
  }, [favIds, list]);

  const recents = useMemo(
    () => [...list].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 5),
    [list]
  );

  const searchResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return list.filter((w) => {
      const title = (w.title || "").toLowerCase();
      const kind = (w.kind || "").toLowerCase();
      return (
        title.includes(q) ||
        kind.includes(q) ||
        kindLabelFor(w.kind, w.template_id).toLowerCase().includes(q)
      );
    });
  }, [list, query, kindLabelFor]);

  const flatItems = useMemo(() => {
    if (searchResults) return searchResults;
    if (useFlatList) return hubsWithItems[0]?.items ?? list;
    return null;
  }, [searchResults, useFlatList, hubsWithItems, list]);

  const toggleFav = (id: string) => {
    setFavIds((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return Array.from(s);
    });
  };

  const toggleHub = (hubId: DashboardHubId) => {
    setCollapsedHubs((prev) => {
      const next = new Set(prev);
      if (next.has(hubId)) next.delete(hubId);
      else next.add(hubId);
      return next;
    });
  };

  const navigableItems = useMemo(() => {
    if (flatItems) return flatItems;
    const out: DashboardSummary[] = [];
    for (const h of hubsWithItems) {
      if (collapsedHubs.has(h.id)) continue;
      out.push(...(grouped[h.id]?.items ?? []));
    }
    return out;
  }, [flatItems, hubsWithItems, grouped, collapsedHubs]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => clamp(i + 1, 0, Math.max(0, navigableItems.length - 1)));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => clamp(i - 1, 0, Math.max(0, navigableItems.length - 1)));
      return;
    }
    if (e.key === "Enter") {
      const id = navigableItems[activeIndex]?.id;
      if (id) {
        e.preventDefault();
        onSelectDashboard(id);
      }
      return;
    }
    if (e.key === "Escape" && query) {
      e.preventDefault();
      setQuery("");
    }
  };

  useEffect(() => {
    const el = itemRefs.current[activeIndex];
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (list.length === 0) return null;

  const rowProps = (w: DashboardSummary) => ({
    w,
    selected: selectedId === w.id,
    fav: favIds.includes(w.id),
    kindLabel: kindLabelFor(w.kind, w.template_id),
    unread: dashboardUnreadCount?.(w.id) ?? 0,
    onSelect: () => onSelectDashboard(w.id),
    onToggleFav: () => toggleFav(w.id),
  });

  const renderShortcutRow = (w: DashboardSummary, key: string) => (
    <DashboardNavRow key={key} {...rowProps(w)} active={false} />
  );

  const renderPrimaryRow = (w: DashboardSummary, idx: number) => (
    <DashboardNavRow
      key={w.id}
      {...rowProps(w)}
      active={idx === activeIndex}
      buttonRef={(el) => {
        itemRefs.current[idx] = el;
      }}
    />
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col" onKeyDown={onKeyDown}>
      {showSearch ? (
        <div className="shrink-0 border-b border-surface-border px-2 py-2">
          <input
            className="dashboard-grid-no-drag w-full rounded-md border border-surface-border bg-black/30 px-2.5 py-1.5 text-xs text-white outline-none focus:border-sky-500/50"
            placeholder={t("dashboard:searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-2">
        {favorites.length > 0 && !query.trim() ? (
          <section className="mb-3">
            <p className="mb-1 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/40">
              {t("dashboard:favorites")}
            </p>
            <ul className="space-y-0.5">
              {favorites.map((w) => renderShortcutRow(w, `fav-${w.id}`))}
            </ul>
          </section>
        ) : null}

        {showRecent ? (
          <section className="mb-3">
            <p className="mb-1 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/40">
              {t("dashboard:recent")}
            </p>
            <ul className="space-y-0.5">
              {recents.map((w) => renderShortcutRow(w, `recent-${w.id}`))}
            </ul>
          </section>
        ) : null}

        {searchResults ? (
          <section>
            <p className="mb-1 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/40">
              {t("dashboard:matches", { count: searchResults.length })}
            </p>
            {searchResults.length === 0 ? (
              <p className="px-2 py-4 text-center text-xs text-surface-muted">{t("dashboard:noDashboardsInHub")}</p>
            ) : (
              <ul className="space-y-0.5">
                {searchResults.map((w, idx) => renderPrimaryRow(w, idx))}
              </ul>
            )}
          </section>
        ) : flatItems ? (
          <section>
            {!useFlatList || list.length > 1 ? (
              <p className="mb-1 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                {t("dashboard:allDashboards", { count: flatItems.length })}
              </p>
            ) : null}
            <ul className="space-y-0.5">
              {flatItems.map((w, idx) => renderPrimaryRow(w, idx))}
            </ul>
          </section>
        ) : (
          <div className="space-y-2">
            {hubsWithItems.map((h) => {
              const items = grouped[h.id]?.items ?? [];
              const collapsed = collapsedHubs.has(h.id);
              return (
                <section key={h.id}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-1 rounded-md px-1.5 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-white/45 hover:bg-white/5 hover:text-white/70"
                    onClick={() => toggleHub(h.id)}
                    aria-expanded={!collapsed}
                  >
                    <span className="w-3 shrink-0 text-white/30">{collapsed ? "▸" : "▾"}</span>
                    <span className="min-w-0 flex-1 truncate">{h.label}</span>
                    <span className="shrink-0 text-white/25">({items.length})</span>
                  </button>
                  {!collapsed ? (
                    <ul className="mt-0.5 space-y-0.5">
                      {items.map((w) => {
                        const idx = navigableItems.findIndex((x) => x.id === w.id);
                        return renderPrimaryRow(w, idx >= 0 ? idx : 0);
                      })}
                    </ul>
                  ) : null}
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
