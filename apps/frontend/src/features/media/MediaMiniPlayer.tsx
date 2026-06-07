import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { itemLabel } from "./mediaTypes";
import { useOptionalGlobalMedia } from "./GlobalMediaProvider";
import { MediaMiniPlayerPanel } from "./MediaMiniPlayerPanel";
import { mediaCanPlay, mediaPlaysEmbed } from "./mediaPlayerPlayback";

export function MediaMiniPlayer() {
  const { t } = useTranslation(["dashboard"]);
  const media = useOptionalGlobalMedia();
  const [embedExpanded, setEmbedExpanded] = useState(false);

  useEffect(() => {
    if (!media?.embedUrl) setEmbedExpanded(false);
  }, [media?.embedUrl]);

  if (!media?.libraryEnabled) return null;

  const hasTrack = media.active && media.nowItem != null;
  const canPlay = hasTrack || media.queue.items.some((it) => mediaCanPlay(it));
  const label = hasTrack
    ? itemLabel(media.nowItem!, t("dashboard:mediaUntitledTrack"))
    : media.queue.items.length > 0
      ? itemLabel(
          media.queue.items.find((it) => mediaCanPlay(it)) ?? media.queue.items[0]!,
          t("dashboard:mediaMiniPlayerIdleTitle")
        )
      : t("dashboard:mediaMiniPlayerIdleTitle");
  const isPersistentAudio =
    hasTrack &&
    (media.uploadMediaId != null || media.nowItem?.source_kind === "external_link");
  const isEmbed = hasTrack && mediaPlaysEmbed(media.nowItem);
  const dashboardHref = media.binding?.dashboardId
    ? `/dashboard?id=${encodeURIComponent(media.binding.dashboardId)}`
    : null;

  const statusHint = (() => {
    if (media.playbackError === "play_blocked") return t("dashboard:mediaFooterPlayBlocked");
    if (media.playbackError === "stream_error") return t("dashboard:mediaFooterStreamError");
    if (!hasTrack) {
      return media.queue.items.length > 0
        ? t("dashboard:mediaFooterQueueReady")
        : t("dashboard:mediaMiniPlayerIdleHint");
    }
    if (media.streamLoading) return t("dashboard:mediaStreamLoading");
    if (isPersistentAudio) {
      return media.nowItem?.source_kind === "external_link"
        ? t("dashboard:mediaMiniPlayerStreamHint")
        : t("dashboard:mediaMiniPlayerUploadHint");
    }
    if (isEmbed) {
      if (media.paused) return t("dashboard:mediaMiniPlayerEmbedPaused");
      if (!embedExpanded) return t("dashboard:mediaMiniPlayerEmbedCollapsedHint");
      return t("dashboard:mediaMiniPlayerEmbedHint");
    }
    return t("dashboard:mediaMiniPlayerIdleHint");
  })();

  return (
    <div
      className="shrink-0 border-t border-sky-500/30 bg-sky-950/50"
      role="region"
      aria-label={
        hasTrack ? t("dashboard:mediaMiniPlayerRegion") : t("dashboard:mediaMiniPlayerRegionIdle")
      }
    >
      {media.panelOpen ? <MediaMiniPlayerPanel media={media} /> : null}
      {media.embedUrl ? (
        <div
          className={
            embedExpanded
              ? "border-b border-sky-500/20 bg-black/60 px-3 py-2"
              : "fixed h-0 w-0 overflow-hidden opacity-0 pointer-events-none"
          }
          aria-hidden={!embedExpanded}
        >
          <div className="mx-auto aspect-video max-h-36 max-w-md overflow-hidden rounded-md">
            <iframe
              title={label}
              src={media.embedUrl}
              className="h-full w-full border-0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        </div>
      ) : null}
      <div className="px-3 py-2">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3">
          <button
            type="button"
            className={`shrink-0 rounded-md px-2 py-1.5 text-xs font-medium ${
              media.panelOpen
                ? "bg-sky-600/50 text-white"
                : "border border-sky-500/30 text-sky-100 hover:bg-sky-900/40"
            }`}
            onClick={() => media.setPanelOpen(!media.panelOpen)}
            aria-expanded={media.panelOpen}
          >
            {t("dashboard:mediaFooterBrowse")}
          </button>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{label}</p>
            <p className="truncate text-[11px] text-surface-muted">
              {statusHint}
              {media.binding?.dashboardTitle ? (
                <span className="text-white/40"> · {media.binding.dashboardTitle}</span>
              ) : null}
            </p>
          </div>

          <label className="flex shrink-0 items-center gap-2 text-[11px] text-surface-muted">
            <span className="hidden sm:inline">{t("dashboard:mediaMiniPlayerVolume")}</span>
            <span aria-hidden>🔊</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={media.volume}
              onChange={(e) => media.setVolume(Number(e.target.value))}
              className="h-1.5 w-20 cursor-pointer accent-sky-400 sm:w-24"
              aria-label={t("dashboard:mediaMiniPlayerVolume")}
            />
          </label>

          <div className="flex shrink-0 items-center gap-1">
            {isEmbed && media.embedUrl ? (
              <button
                type="button"
                className="rounded-md border border-white/10 px-2 py-1.5 text-xs text-sky-100 hover:bg-white/10"
                onClick={() => setEmbedExpanded((open) => !open)}
                aria-expanded={embedExpanded}
                aria-label={
                  embedExpanded
                    ? t("dashboard:mediaMiniPlayerEmbedCollapse")
                    : t("dashboard:mediaMiniPlayerEmbedExpand")
                }
              >
                {embedExpanded
                  ? t("dashboard:mediaMiniPlayerEmbedCollapse")
                  : t("dashboard:mediaMiniPlayerEmbedExpand")}
              </button>
            ) : null}
            <button
              type="button"
              className="rounded-md px-2 py-1.5 text-xs text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              onClick={media.playPrev}
              disabled={!canPlay}
              aria-label={t("dashboard:mediaMiniPlayerPrev")}
            >
              ⏮
            </button>
            <button
              type="button"
              className="rounded-md bg-white/15 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/20 disabled:opacity-40"
              onClick={media.togglePause}
              disabled={!canPlay || (isPersistentAudio && media.streamLoading)}
              aria-label={
                hasTrack && !media.paused
                  ? t("dashboard:mediaMiniPlayerPause")
                  : t("dashboard:mediaMiniPlayerPlay")
              }
            >
              {hasTrack && !media.paused ? "⏸" : "▶"}
            </button>
            <button
              type="button"
              className="rounded-md px-2 py-1.5 text-xs text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              onClick={media.playNext}
              disabled={!canPlay}
              aria-label={t("dashboard:mediaMiniPlayerNext")}
            >
              ⏭
            </button>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {dashboardHref ? (
              <Link
                to={dashboardHref}
                className="rounded-md border border-white/10 px-2 py-1 text-[11px] text-sky-100 hover:bg-white/5"
              >
                {t("dashboard:mediaMiniPlayerOpenDashboard")}
              </Link>
            ) : null}
            <button
              type="button"
              className="rounded-md px-2 py-1 text-[11px] text-surface-muted hover:bg-white/5 hover:text-neutral-200 disabled:opacity-40"
              onClick={media.stop}
              disabled={!hasTrack}
              aria-label={t("dashboard:mediaMiniPlayerStop")}
            >
              {t("dashboard:mediaMiniPlayerStop")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
