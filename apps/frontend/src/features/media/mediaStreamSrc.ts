import type { MediaQueueItem } from "./mediaTypes";
import { mediaIdFromRef } from "../dashboard/media/useMediaStreamUrl";
import { mediaPlaysAudio } from "./mediaPlayerPlayback";
import { mediaLog } from "./mediaPlaybackLog";

/** Same-origin stream URL for uploads (auth via query token — no Bearer on media elements). */
export function mediaItemStreamSrc(mediaId: string | null, accessToken: string | null): string | null {
  const id = (mediaId || "").trim();
  const tok = (accessToken || "").trim();
  if (!id || !tok) return null;
  return `/v1/media/items/${encodeURIComponent(id)}/stream?token=${encodeURIComponent(tok)}`;
}

/** Radio/https streams play from the browser; uploads use the authenticated API stream. */
export function mediaPlayerAudioSrc(
  item: MediaQueueItem | null,
  accessToken: string | null
): string | null {
  if (!item || !mediaPlaysAudio(item)) {
    mediaLog("mediaPlayerAudioSrc: no audio item", {
      hasItem: Boolean(item),
      source_kind: item?.source_kind ?? null,
    });
    return null;
  }
  if (item.source_kind === "external_link") {
    const direct = item.external_url?.trim() || item.stream_url?.trim();
    if (direct) {
      mediaLog("mediaPlayerAudioSrc: direct external stream", {
        ref: item.ref ?? null,
        url: direct,
      });
      return direct;
    }
    mediaLog("mediaPlayerAudioSrc: external_link missing url, falling back to API", {
      ref: item.ref ?? null,
      external_url: item.external_url ?? null,
      stream_url: item.stream_url ?? null,
    });
  }
  const apiSrc = mediaItemStreamSrc(mediaIdFromRef(item.ref), accessToken);
  mediaLog("mediaPlayerAudioSrc: API stream", { ref: item.ref ?? null, hasToken: Boolean(accessToken?.trim()) });
  return apiSrc;
}
