import type { useAuth } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

type Auth = ReturnType<typeof useAuth>;

export const MEDIA_AUDIO_ACCEPT =
  "audio/mpeg,audio/mp4,audio/flac,audio/ogg,audio/wav,video/mp4";

export async function uploadMediaFile(
  file: File,
  auth: Auth,
  opts: { dashboardId?: string; title?: string; artist?: string },
  t: (key: string, opts?: Record<string, unknown>) => string
): Promise<
  | { ok: true; item: { id: string; media_ref: string; stream_url?: string; title?: string; artist?: string } }
  | { ok: false; error: string }
> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts.title?.trim()) fd.append("title", opts.title.trim());
  if (opts.artist?.trim()) fd.append("artist", opts.artist.trim());
  if (opts.dashboardId?.trim()) fd.append("dashboard_id", opts.dashboardId.trim());
  try {
    const res = await apiFetch("/v1/media/items/upload", auth, { method: "POST", body: fd });
    const raw = await res.text();
    let j: { item?: { id?: string; media_ref?: string; stream_url?: string; title?: string; artist?: string }; detail?: unknown } =
      {};
    try {
      j = JSON.parse(raw) as typeof j;
    } catch {
      j = {};
    }
    if (!res.ok) {
      const msg =
        typeof j.detail === "string" ? j.detail : t("dashboard:uploadFailed", { status: res.status });
      return { ok: false, error: msg };
    }
    const item = j.item;
    if (!item?.id || !item.media_ref) return { ok: false, error: t("dashboard:uploadNoRef") };
    return {
      ok: true,
      item: {
        id: item.id,
        media_ref: item.media_ref,
        stream_url: item.stream_url,
        title: item.title,
        artist: item.artist,
      },
    };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function addMediaEmbed(
  externalUrl: string,
  auth: Auth,
  opts: { dashboardId?: string; title?: string; artist?: string },
  t: (key: string, opts?: Record<string, unknown>) => string
): Promise<
  | { ok: true; item: { id: string; media_ref: string; external_url?: string; title?: string; artist?: string } }
  | { ok: false; error: string }
> {
  try {
    const res = await apiFetch("/v1/media/items/embed", auth, {
      method: "POST",
      body: JSON.stringify({
        external_url: externalUrl.trim(),
        title: opts.title?.trim() || "",
        artist: opts.artist?.trim() || "",
        dashboard_id: opts.dashboardId?.trim() || null,
      }),
    });
    const j = (await res.json()) as {
      item?: { id?: string; media_ref?: string; external_url?: string; title?: string; artist?: string };
      detail?: unknown;
    };
    if (!res.ok) {
      const msg =
        typeof j.detail === "string" ? j.detail : t("dashboard:mediaEmbedFailed", { status: res.status });
      return { ok: false, error: msg };
    }
    const item = j.item;
    if (!item?.id || !item.media_ref) return { ok: false, error: t("dashboard:uploadNoRef") };
    return {
      ok: true,
      item: {
        id: item.id,
        media_ref: item.media_ref,
        external_url: item.external_url,
        title: item.title,
        artist: item.artist,
      },
    };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
