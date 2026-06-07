import type { MediaQueueItem } from "./mediaTypes";

/** Media player plays uploads and HTTPS streams via ``<audio>``. */
export function mediaPlaysAudio(item: MediaQueueItem | null | undefined): boolean {
  if (!item) return false;
  const kind = item.source_kind;
  return kind === "upload" || kind === "external_link";
}

/** Embeds (YouTube/Vimeo) play in the media player via iframe. */
export function mediaPlaysEmbed(item: MediaQueueItem | null | undefined): boolean {
  if (!item) return false;
  return item.source_kind === "embed";
}

/** Whether the global media player can start this queue item. */
export function mediaCanPlay(item: MediaQueueItem | null | undefined): boolean {
  return mediaPlaysAudio(item) || mediaPlaysEmbed(item);
}
