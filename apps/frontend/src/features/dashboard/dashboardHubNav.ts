import type { DashboardSummary } from "./types";

export type DashboardHubId = "pets" | "family" | "media" | "home" | "work" | "other";

export type DashboardHub = {
  id: DashboardHubId;
  label: string;
};

export const DEFAULT_HUBS: DashboardHub[] = [
  { id: "pets", label: "Pets" },
  { id: "family", label: "Family" },
  { id: "media", label: "Media" },
  { id: "home", label: "Home" },
  { id: "work", label: "Work" },
  { id: "other", label: "Other" },
];

export type HubRules = {
  kindToHub?: Partial<Record<string, DashboardHubId>>;
  titleIncludes?: Partial<Record<DashboardHubId, string[]>>;
};

const DEFAULT_KIND_TO_HUB: Record<string, DashboardHubId> = {
  pets: "pets",
  photo_album: "media",
  "photo-album": "media",
  media_station: "media",
  "media-station": "media",
  shopping_list: "home",
  todo: "home",
  tasks: "home",
  ideas: "work",
  projects: "work",
  feeds: "home",
  friends: "family",
  personal_dashboard: "home",
};

const DEFAULT_TITLE_INCLUDES: Record<DashboardHubId, string[]> = {
  pets: ["pet", "pets", "haustier", "tier", "hund", "katze"],
  family: ["family", "fam", "kinder", "kind", "eltern", "friends", "kontakte"],
  media: ["album", "photo", "foto", "gallery", "media", "video", "music", "station", "playlist"],
  home: ["home", "haushalt", "shopping", "einkauf", "todo", "tasks", "putzen", "wohnung"],
  work: ["work", "job", "projekt", "project", "client", "kunden", "meeting"],
  other: [],
};

function norm(s: unknown): string {
  return String(s ?? "").trim().toLowerCase();
}

export function inferHubId(w: DashboardSummary, rules?: HubRules): DashboardHubId {
  const kind = norm(w.kind);
  const title = norm(w.title);

  const map = { ...DEFAULT_KIND_TO_HUB, ...(rules?.kindToHub ?? {}) };
  if (kind && map[kind]) return map[kind]!;

  const byTitle = { ...DEFAULT_TITLE_INCLUDES, ...(rules?.titleIncludes ?? {}) };
  for (const hub of Object.keys(byTitle) as DashboardHubId[]) {
    const keys = byTitle[hub] ?? [];
    if (keys.some((k) => title.includes(k.toLowerCase()))) return hub;
  }
  return "other";
}

export type HubGroup = {
  hub: DashboardHub;
  items: DashboardSummary[];
};

export function groupDashboardsByHub(
  list: DashboardSummary[],
  hubs: DashboardHub[] = DEFAULT_HUBS,
  rules?: HubRules
): Record<DashboardHubId, HubGroup> {
  const out = {} as Record<DashboardHubId, HubGroup>;
  for (const h of hubs) out[h.id] = { hub: h, items: [] };

  for (const w of list) {
    const hid = inferHubId(w, rules);
    (out[hid] ?? out.other).items.push(w);
  }

  for (const g of Object.values(out)) {
    g.items.sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  }
  return out;
}

export function hubForSelectedId(
  grouped: Record<DashboardHubId, HubGroup>,
  selectedId: string | null
): DashboardHubId | null {
  if (!selectedId) return null;
  for (const hid of Object.keys(grouped) as DashboardHubId[]) {
    if (grouped[hid].items.some((w) => w.id === selectedId)) return hid;
  }
  return null;
}

