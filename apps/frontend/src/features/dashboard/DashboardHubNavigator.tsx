import type { KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { DashboardSummary } from "./types";
import type { HubGroup, DashboardHub, DashboardHubId } from "./dashboardHubNav";

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

function pillClass(active: boolean): string {
  return [
    "rounded-lg border px-3 py-1.5 text-xs transition",
    active
      ? "border-white/15 bg-white/10 text-white"
      : "border-surface-border text-surface-muted hover:bg-white/5 hover:text-neutral-200",
  ].join(" ");
}

type Entry = { id: string; label: string; kindLabel: string; accessNote: string; updatedAt: string };

export function DashboardHubNavigator(props: {
  hubs: DashboardHub[];
  grouped: Record<DashboardHubId, HubGroup>;
  activeHubId: DashboardHubId;
  setActiveHubId: (id: DashboardHubId) => void;
  selectedId: string | null;
  onSelectDashboard: (id: string) => void;
  kindLabelFor: (kind: string) => string;
}) {
  const { t } = useTranslation(["dashboard"]);
  const {
    hubs,
    grouped,
    activeHubId,
    setActiveHubId,
    selectedId,
    onSelectDashboard,
    kindLabelFor,
  } = props;

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const [favIds, setFavIds] = useState<string[]>(() => (typeof window === "undefined" ? [] : loadFavs()));

  useEffect(() => {
    saveFavs(favIds);
  }, [favIds]);

  useEffect(() => {
    setActiveIndex(0);
  }, [activeHubId, query]);

  const hubItems = grouped[activeHubId]?.items ?? [];

  const favorites = useMemo(() => {
    const s = new Set(favIds);
    const byId = new Map(hubItems.map((w) => [w.id, w]));
    return favIds
      .map((id) => byId.get(id))
      .filter((w): w is DashboardSummary => !!w)
      .filter((w) => s.has(w.id));
  }, [favIds, hubItems]);

  const recents = useMemo(() => hubItems.slice(0, 6), [hubItems]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return hubItems;
    return hubItems.filter((w) => {
      const t = (w.title || "").toLowerCase();
      const k = (w.kind || "").toLowerCase();
      return t.includes(q) || k.includes(q) || kindLabelFor(w.kind).toLowerCase().includes(q);
    });
  }, [hubItems, query, kindLabelFor]);

  const listEntries = useMemo(() => {
    const mk = (w: DashboardSummary): Entry => ({
      id: w.id,
      label: w.title || w.kind,
      kindLabel: kindLabelFor(w.kind),
      accessNote:
        w.access_role === "viewer"
          ? "read-only"
          : w.access_role === "editor"
            ? "shared"
            : w.access_role === "co_owner"
              ? "co-owner"
              : "",
      updatedAt: w.updated_at,
    });
    return filtered.map(mk);
  }, [filtered, kindLabelFor]);

  const toggleFav = (id: string) => {
    setFavIds((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return Array.from(s);
    });
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => clamp(i + 1, 0, Math.max(0, listEntries.length - 1)));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => clamp(i - 1, 0, Math.max(0, listEntries.length - 1)));
      return;
    }
    if (e.key === "Enter") {
      const id = listEntries[activeIndex]?.id;
      if (id) {
        e.preventDefault();
        onSelectDashboard(id);
      }
      return;
    }
    if (e.key === "Escape") {
      if (query) {
        e.preventDefault();
        setQuery("");
      }
    }
  };

  useEffect(() => {
    const el = itemRefs.current[activeIndex];
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-raised/50 p-3 md:p-4" onKeyDown={onKeyDown}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {hubs.map((h) => (
            <button
              key={h.id}
              type="button"
              className={pillClass(h.id === activeHubId)}
              onClick={() => setActiveHubId(h.id)}
            >
              {h.label}
              <span className="ml-2 text-[10px] text-white/35">({grouped[h.id]?.items.length ?? 0})</span>
            </button>
          ))}
        </div>
        <div className="min-w-[220px] flex-1 lg:max-w-sm">
          <input
            className="dashboard-grid-no-drag w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
            placeholder={t("dashboard:searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {favorites.length ? (
        <div className="mt-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-white/40">
            {t("dashboard:favorites")}
          </p>
          <div className="flex flex-wrap gap-2">
            {favorites.map((w) => (
              <button
                key={w.id}
                type="button"
                className={[
                  "rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5",
                  selectedId === w.id ? "border-sky-500/40" : "",
                ].join(" ")}
                onClick={() => onSelectDashboard(w.id)}
              >
                {w.title || w.kind}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {!query && recents.length ? (
        <div className="mt-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-white/40">
            {t("dashboard:recent")}
          </p>
          <div className="flex flex-wrap gap-2">
            {recents.map((w) => (
              <button
                key={w.id}
                type="button"
                className={[
                  "rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5",
                  selectedId === w.id ? "border-sky-500/40" : "",
                ].join(" ")}
                onClick={() => onSelectDashboard(w.id)}
              >
                {w.title || w.kind}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
            {query
              ? t("dashboard:matches", { count: listEntries.length })
              : t("dashboard:allInHub", {
                  hub: grouped[activeHubId]?.hub.label ?? t("dashboard:hubFallback"),
                  count: listEntries.length,
                })}
          </p>
          <p className="text-[10px] text-white/25">{t("dashboard:kbdHint")}</p>
        </div>
        <div
          ref={listRef}
          className="max-h-[min(46vh,420px)] overflow-y-auto rounded-lg border border-white/10 bg-black/20"
        >
          {listEntries.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-surface-muted">
              {t("dashboard:noDashboardsInHub")}
            </p>
          ) : (
            <ul className="divide-y divide-white/5">
              {listEntries.map((e, idx) => {
                const isSelected = selectedId === e.id;
                const isActive = idx === activeIndex;
                const fav = favIds.includes(e.id);
                return (
                  <li key={e.id} className="flex items-stretch gap-1">
                    <button
                      ref={(el) => {
                        itemRefs.current[idx] = el;
                      }}
                      type="button"
                      className={[
                        "min-w-0 flex-1 px-3 py-2 text-left text-sm outline-none",
                        isSelected ? "text-white" : "text-neutral-200",
                        isActive ? "bg-white/10" : "hover:bg-white/5",
                      ].join(" ")}
                      onClick={() => onSelectDashboard(e.id)}
                    >
                      <span className="block truncate font-medium">{e.label}</span>
                      <span className="block truncate text-[10px] text-white/35">
                        {e.kindLabel}
                        {e.accessNote ? ` · ${e.accessNote}` : ""}
                      </span>
                    </button>
                    <button
                      type="button"
                      title={fav ? t("dashboard:unfavorite") : t("dashboard:favorite")}
                      className={[
                        "shrink-0 px-3 text-sm",
                        fav ? "text-amber-300/90 hover:bg-amber-950/30" : "text-white/25 hover:bg-white/5 hover:text-white/50",
                      ].join(" ")}
                      onClick={() => toggleFav(e.id)}
                    >
                      {fav ? "★" : "☆"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

