import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { itemLabel } from "./mediaTypes";
import { useOptionalGlobalMedia } from "./GlobalMediaProvider";

export function MediaMiniPlayer() {
  const { t } = useTranslation(["dashboard"]);
  const media = useOptionalGlobalMedia();

  if (!media?.active || !media.nowItem) return null;

  const label = itemLabel(media.nowItem, t("dashboard:mediaUntitledTrack"));
  const isPersistentAudio =
    media.uploadMediaId != null || media.nowItem?.source_kind === "external_link";
  const dashboardHref = media.binding?.dashboardId
    ? `/dashboard?id=${encodeURIComponent(media.binding.dashboardId)}`
    : null;

  return (
    <div
      className="shrink-0 border-t border-sky-500/30 bg-sky-950/50 px-3 py-2"
      role="region"
      aria-label={t("dashboard:mediaMiniPlayerRegion")}
    >
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{label}</p>
          <p className="truncate text-[11px] text-surface-muted">
            {media.streamLoading
              ? t("dashboard:mediaStreamLoading")
              : isPersistentAudio
                ? media.nowItem?.source_kind === "external_link"
                  ? t("dashboard:mediaMiniPlayerStreamHint")
                  : t("dashboard:mediaMiniPlayerUploadHint")
                : t("dashboard:mediaMiniPlayerEmbedHint")}
            {media.binding?.dashboardTitle ? (
              <span className="text-white/40"> · {media.binding.dashboardTitle}</span>
            ) : null}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="rounded-md px-2 py-1.5 text-xs text-neutral-200 hover:bg-white/10"
            onClick={media.playPrev}
            aria-label={t("dashboard:mediaMiniPlayerPrev")}
          >
            ⏮
          </button>
          <button
            type="button"
            className="rounded-md bg-white/15 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/20 disabled:opacity-50"
            onClick={media.togglePause}
            disabled={isPersistentAudio && media.streamLoading}
            aria-label={
              media.paused ? t("dashboard:mediaMiniPlayerPlay") : t("dashboard:mediaMiniPlayerPause")
            }
          >
            {media.paused ? "▶" : "⏸"}
          </button>
          <button
            type="button"
            className="rounded-md px-2 py-1.5 text-xs text-neutral-200 hover:bg-white/10"
            onClick={media.playNext}
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
            className="rounded-md px-2 py-1 text-[11px] text-surface-muted hover:bg-white/5 hover:text-neutral-200"
            onClick={media.stop}
            aria-label={t("dashboard:mediaMiniPlayerStop")}
          >
            {t("dashboard:mediaMiniPlayerStop")}
          </button>
        </div>
      </div>
    </div>
  );
}
