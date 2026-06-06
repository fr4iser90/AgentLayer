import { mediaIdFromRef } from "../dashboard/media/useMediaStreamUrl";

export type MediaQueueItem = {
  ref?: string;
  title?: string;
  artist?: string;
  source_kind?: "upload" | "embed" | "external_link" | "archive";
  external_url?: string;
  stream_url?: string;
};

export type MediaQueueState = {
  now_playing_id: string | null;
  items: MediaQueueItem[];
  shuffle: boolean;
  repeat: "off" | "one" | "all";
};

export type MediaSessionBinding = {
  dashboardId: string;
  dataPath: string;
  dashboardTitle?: string;
};

export function readQueue(raw: unknown): MediaQueueState {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const itemsRaw = o.items;
    const items: MediaQueueItem[] = Array.isArray(itemsRaw)
      ? itemsRaw
          .filter((x) => x && typeof x === "object")
          .map((x) => {
            const r = x as Record<string, unknown>;
            return {
              ref: String(r.ref ?? "").trim() || undefined,
              title: String(r.title ?? "").trim(),
              artist: String(r.artist ?? "").trim(),
              source_kind: r.source_kind as MediaQueueItem["source_kind"],
              external_url: String(r.external_url ?? "").trim() || undefined,
              stream_url: String(r.stream_url ?? "").trim() || undefined,
            };
          })
      : [];
    const rep = String(o.repeat ?? "off");
    return {
      now_playing_id: o.now_playing_id != null ? String(o.now_playing_id) : null,
      items,
      shuffle: Boolean(o.shuffle),
      repeat: rep === "one" || rep === "all" ? rep : "off",
    };
  }
  return { now_playing_id: null, items: [], shuffle: false, repeat: "off" };
}

export function itemId(item: MediaQueueItem): string | null {
  return mediaIdFromRef(item.ref) || item.ref?.trim() || null;
}

export function itemLabel(item: MediaQueueItem, fallback: string): string {
  const title = item.title?.trim();
  if (title) return item.artist?.trim() ? `${title} — ${item.artist.trim()}` : title;
  return fallback;
}

export function resolveNowItem(state: MediaQueueState): MediaQueueItem | null {
  if (!state.items.length) return null;
  if (!state.now_playing_id) return state.items[0] ?? null;
  return state.items.find((it) => itemId(it) === state.now_playing_id) ?? state.items[0] ?? null;
}

export function nextQueueItem(state: MediaQueueState, currentId: string | null): MediaQueueItem | null {
  const { items, shuffle, repeat } = state;
  if (!items.length) return null;
  if (repeat === "one" && currentId) {
    return items.find((it) => itemId(it) === currentId) ?? items[0] ?? null;
  }
  const curIdx = currentId ? items.findIndex((it) => itemId(it) === currentId) : -1;
  if (shuffle) {
    if (items.length === 1) return items[0] ?? null;
    let pick = Math.floor(Math.random() * items.length);
    if (pick === curIdx) pick = (pick + 1) % items.length;
    return items[pick] ?? null;
  }
  const nextIdx = curIdx < 0 ? 0 : curIdx + 1;
  if (nextIdx < items.length) return items[nextIdx] ?? null;
  if (repeat === "all") return items[0] ?? null;
  return null;
}

export function prevQueueItem(state: MediaQueueState, currentId: string | null): MediaQueueItem | null {
  const { items, shuffle } = state;
  if (!items.length) return null;
  const curIdx = currentId ? items.findIndex((it) => itemId(it) === currentId) : -1;
  if (shuffle) {
    if (items.length === 1) return items[0] ?? null;
    let pick = Math.floor(Math.random() * items.length);
    if (pick === curIdx) pick = (pick + items.length - 1) % items.length;
    return items[pick] ?? null;
  }
  if (curIdx > 0) return items[curIdx - 1] ?? null;
  return items[items.length - 1] ?? null;
}
