import type { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { MediaQueueItem } from "./mediaTypes";

type Auth = ReturnType<typeof useAuth>;

export type MediaLibraryItem = {
  id: string;
  media_ref: string;
  source_kind: "upload" | "embed" | "external_link" | "archive" | string;
  title?: string;
  artist?: string;
  album?: string;
  external_url?: string;
  stream_url?: string;
  embed_provider?: string;
  original_name?: string;
  created_at?: string;
};

export type MediaLibraryFilter = "all" | "external_link" | "upload" | "embed";

export function queueItemFromLibrary(item: MediaLibraryItem): MediaQueueItem {
  return {
    ref: item.media_ref,
    title: item.title || "",
    artist: item.artist || "",
    source_kind:
      item.source_kind === "upload" ||
      item.source_kind === "embed" ||
      item.source_kind === "external_link" ||
      item.source_kind === "archive"
        ? item.source_kind
        : "external_link",
    external_url: item.external_url?.trim() || undefined,
    stream_url: item.stream_url?.trim() || undefined,
  };
}

export function libraryItemLabel(item: MediaLibraryItem, fallback: string): string {
  const title = item.title?.trim() || item.original_name?.trim();
  if (title) return item.artist?.trim() ? `${title} — ${item.artist.trim()}` : title;
  if (item.external_url?.trim()) return item.external_url.trim();
  return fallback;
}

export async function fetchMediaLibraryItems(
  auth: Auth,
  filter: MediaLibraryFilter
): Promise<{ ok: true; items: MediaLibraryItem[] } | { ok: false; error: string }> {
  try {
    const qs =
      filter === "all" ? "" : `?source_kind=${encodeURIComponent(filter)}`;
    const res = await apiFetch(`/v1/media/items${qs}`, auth);
    const j = (await res.json()) as { items?: MediaLibraryItem[]; detail?: unknown };
    if (!res.ok) {
      return {
        ok: false,
        error: typeof j.detail === "string" ? j.detail : `HTTP ${res.status}`,
      };
    }
    return { ok: true, items: Array.isArray(j.items) ? j.items : [] };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function addMediaStreamUrl(
  auth: Auth,
  opts: { streamUrl: string; title?: string; artist?: string; dashboardId?: string }
): Promise<{ ok: true; item: MediaLibraryItem } | { ok: false; error: string }> {
  try {
    const res = await apiFetch("/v1/media/items/stream", auth, {
      method: "POST",
      body: JSON.stringify({
        stream_url: opts.streamUrl.trim(),
        title: opts.title?.trim() || "",
        artist: opts.artist?.trim() || "",
        dashboard_id: opts.dashboardId?.trim() || null,
      }),
    });
    const j = (await res.json()) as { item?: MediaLibraryItem; detail?: unknown };
    if (!res.ok || !j.item?.media_ref) {
      return {
        ok: false,
        error: typeof j.detail === "string" ? j.detail : `HTTP ${res.status}`,
      };
    }
    return { ok: true, item: j.item };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function deleteMediaLibraryItem(
  auth: Auth,
  mediaItemId: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  const id = mediaItemId.trim();
  if (!id) return { ok: false, error: "missing media item id" };
  try {
    const res = await apiFetch(`/v1/media/items/${encodeURIComponent(id)}`, auth, {
      method: "DELETE",
    });
    if (!res.ok) {
      const j = (await res.json().catch(() => ({}))) as { detail?: unknown };
      return {
        ok: false,
        error: typeof j.detail === "string" ? j.detail : `HTTP ${res.status}`,
      };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function addMediaEmbedUrl(
  auth: Auth,
  opts: { externalUrl: string; title?: string; artist?: string; dashboardId?: string },
  t: (key: string, opts?: Record<string, unknown>) => string
): Promise<{ ok: true; item: MediaLibraryItem } | { ok: false; error: string }> {
  try {
    const res = await apiFetch("/v1/media/items/embed", auth, {
      method: "POST",
      body: JSON.stringify({
        external_url: opts.externalUrl.trim(),
        title: opts.title?.trim() || "",
        artist: opts.artist?.trim() || "",
        dashboard_id: opts.dashboardId?.trim() || null,
      }),
    });
    const j = (await res.json()) as { item?: MediaLibraryItem; detail?: unknown };
    if (!res.ok || !j.item?.media_ref) {
      const msg =
        typeof j.detail === "string" ? j.detail : t("dashboard:mediaEmbedFailed", { status: res.status });
      return { ok: false, error: msg };
    }
    return { ok: true, item: j.item };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
