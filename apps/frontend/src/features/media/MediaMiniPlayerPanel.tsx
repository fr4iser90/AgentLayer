import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../ui/Button";
import { useAuth } from "../../auth/AuthContext";
import { embedUrlAllowed } from "../dashboard/EmbedBlock";
import {
  addMediaEmbedUrl,
  addMediaStreamUrl,
  libraryItemLabel,
  type MediaLibraryFilter,
} from "./mediaLibraryApi";
import { uploadMediaFile, MEDIA_AUDIO_ACCEPT } from "../dashboard/media/mediaUpload";
import { mediaCanPlay } from "./mediaPlayerPlayback";
import type { GlobalMediaContextValue } from "./GlobalMediaProvider";
import { itemId, itemLabel } from "./mediaTypes";

type Tab = "queue" | "library";

const FILTERS: MediaLibraryFilter[] = ["all", "external_link", "upload", "embed"];

export function MediaMiniPlayerPanel(props: { media: GlobalMediaContextValue }) {
  const { media } = props;
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const [tab, setTab] = useState<Tab>("library");
  const [streamUrl, setStreamUrl] = useState("");
  const [embedUrl, setEmbedUrl] = useState("");
  const [addTitle, setAddTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const dashId = media.binding?.dashboardId;

  const runAdd = useCallback(
    async (fn: () => Promise<{ ok: boolean; error?: string }>) => {
      setBusy(true);
      setErr(null);
      try {
        const result = await fn();
        if (!result.ok && result.error) setErr(result.error);
        await media.refreshLibrary();
      } finally {
        setBusy(false);
      }
    },
    [media]
  );

  const onAddStream = () => {
    const url = streamUrl.trim();
    if (!url) return;
    void runAdd(async () => {
      const result = await addMediaStreamUrl(auth, {
        streamUrl: url,
        title: addTitle,
        dashboardId: dashId,
      });
      if (!result.ok) return result;
      setStreamUrl("");
      setAddTitle("");
      const play = await media.playLibraryItem(result.item);
      if (!play.ok) return play;
      return { ok: true };
    });
  };

  const onAddEmbed = () => {
    const url = embedUrl.trim();
    if (!url || !embedUrlAllowed(url)) {
      setErr(t("dashboard:embedUrlNotAllowed"));
      return;
    }
    void runAdd(async () => {
      const result = await addMediaEmbedUrl(
        auth,
        { externalUrl: url, title: addTitle, dashboardId: dashId },
        t
      );
      if (!result.ok) return result;
      setEmbedUrl("");
      setAddTitle("");
      const play = await media.playLibraryItem(result.item);
      return { ok: play.ok, error: play.error };
    });
  };

  const onUpload = (file: File) => {
    void runAdd(async () => {
      const result = await uploadMediaFile(file, auth, { dashboardId: dashId, title: addTitle }, t);
      if (!result.ok) return result;
      const play = await media.playLibraryItem({
        id: result.item.id,
        media_ref: result.item.media_ref,
        source_kind: "upload",
        title: result.item.title,
        artist: result.item.artist,
        stream_url: result.item.stream_url,
      });
      return play;
    });
  };

  const filterLabel = (f: MediaLibraryFilter) => {
    if (f === "all") return t("dashboard:mediaFooterFilterAll");
    if (f === "external_link") return t("dashboard:mediaFooterFilterRadio");
    if (f === "upload") return t("dashboard:mediaFooterFilterSongs");
    return t("dashboard:mediaFooterFilterEmbed");
  };

  return (
    <div className="max-h-[min(42vh,320px)] overflow-y-auto border-b border-sky-500/20 bg-sky-950/80 px-soft py-base">
      <div className="mx-auto max-w-page space-y-base">
        <div className="flex flex-wrap items-center gap-base">
          <div className="flex rounded-tile border border-line p-hair text-meta">
            <button
              type="button"
              className={`rounded-tile px-base py-tight ${tab === "queue" ? "bg-white/15 text-white" : "text-ink-muted hover:text-neutral-200"}`}
              onClick={() => setTab("queue")}
            >
              {t("dashboard:mediaFooterTabQueue")} ({media.queue.items.length})
            </button>
            <button
              type="button"
              className={`rounded-tile px-base py-tight ${tab === "library" ? "bg-white/15 text-white" : "text-ink-muted hover:text-neutral-200"}`}
              onClick={() => setTab("library")}
            >
              {t("dashboard:mediaFooterTabLibrary")}
            </button>
          </div>
          <div className="ml-auto flex gap-tight">
            <button
              type="button"
              className={`rounded-tile px-base py-hair text-meta ${media.queue.shuffle ? "bg-sky-600/40 text-white" : "text-ink-muted hover:bg-white/5"}`}
              onClick={media.toggleShuffle}
            >
              {t("dashboard:mediaFooterShuffle")}
            </button>
            <button
              type="button"
              className="rounded-tile px-base py-hair text-meta text-ink-muted hover:bg-white/5"
              onClick={() => {
                const next =
                  media.queue.repeat === "off"
                    ? "all"
                    : media.queue.repeat === "all"
                      ? "one"
                      : "off";
                media.setRepeat(next);
              }}
            >
              {media.queue.repeat === "one"
                ? t("dashboard:mediaFooterRepeatOne")
                : media.queue.repeat === "all"
                  ? t("dashboard:mediaFooterRepeatAll")
                  : t("dashboard:mediaFooterRepeatOff")}
            </button>
          </div>
        </div>

        {tab === "queue" ? (
          <ul className="space-y-hair">
            {media.queue.items.length === 0 ? (
              <li className="py-base text-xs text-ink-muted">{t("dashboard:mediaQueueEmpty")}</li>
            ) : (
              media.queue.items.map((it, idx) => {
                const id = itemId(it);
                const playing = id != null && id === media.queue.now_playing_id && media.active;
                return (
                  <li
                    key={`${id ?? idx}-${idx}`}
                    className={`flex items-center gap-base rounded-tile px-base py-snug text-xs ${
                      playing ? "bg-sky-800/50 text-sky-50" : "text-ink-primary hover:bg-white/5"
                    }`}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 truncate text-left"
                      onClick={() => media.playQueueItem(it)}
                    >
                      {itemLabel(it, t("dashboard:mediaUntitledTrack"))}
                      {!mediaCanPlay(it) ? (
                        <span className="ml-tight text-meta text-ink-muted">({t("dashboard:mediaFooterFilterEmbed")})</span>
                      ) : null}
                    </button>
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      className="shrink-0"
                      onClick={() => media.removeFromQueue(idx)}
                    >
                      {t("dashboard:delete")}
                    </Button>
                  </li>
                );
              })
            )}
          </ul>
        ) : (
          <>
            <div className="flex flex-wrap gap-tight">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  className={`rounded-pill px-base py-hair text-meta ${
                    media.libraryFilter === f
                      ? "bg-sky-600/50 text-ink-primary"
                      : "border border-line text-ink-muted hover:bg-white/5"
                  }`}
                  onClick={() => media.setLibraryFilter(f)}
                >
                  {filterLabel(f)}
                </button>
              ))}
            </div>

            <div className="space-y-snug rounded-card border border-line bg-black/30 p-base">
              <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                {t("dashboard:mediaFooterAddRadio")}
              </p>
              <div className="flex flex-wrap gap-tight">
                <input
                  type="url"
                  value={streamUrl}
                  onChange={(e) => setStreamUrl(e.target.value)}
                  placeholder={t("dashboard:mediaFooterStreamPlaceholder")}
                  className="min-w-[10rem] flex-1 rounded-tile border border-line bg-field px-base py-tight font-mono text-meta text-ink-primary"
                />
                <input
                  type="text"
                  value={addTitle}
                  onChange={(e) => setAddTitle(e.target.value)}
                  placeholder={t("dashboard:mediaFooterTitlePlaceholder")}
                  className="w-28 rounded-tile border border-line bg-field px-base py-tight text-meta text-ink-primary"
                />
                <button
                  type="button"
                  disabled={busy || !streamUrl.trim()}
                  className="rounded-tile bg-sky-700/60 px-base py-tight text-meta text-ink-primary hover:bg-sky-600/60 disabled:opacity-40"
                  onClick={onAddStream}
                >
                  {t("dashboard:mediaFooterAddPlay")}
                </button>
              </div>
              <div className="flex flex-wrap gap-tight">
                <input
                  type="url"
                  value={embedUrl}
                  onChange={(e) => setEmbedUrl(e.target.value)}
                  placeholder={t("dashboard:embedUrlPlaceholder")}
                  className="min-w-[10rem] flex-1 rounded-tile border border-line bg-field px-base py-tight font-mono text-meta text-ink-primary"
                />
                <button
                  type="button"
                  disabled={busy || !embedUrl.trim()}
                  className="rounded-tile border border-line-strong px-base py-tight text-meta text-ink-primary hover:bg-white/5 disabled:opacity-40"
                  onClick={onAddEmbed}
                >
                  {t("dashboard:mediaAddEmbed")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-tile border border-line-strong px-base py-tight text-meta text-ink-primary hover:bg-white/5 disabled:opacity-40"
                  onClick={() => fileRef.current?.click()}
                >
                  {t("dashboard:mediaUploadTrack")}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept={MEDIA_AUDIO_ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) onUpload(f);
                  }}
                />
              </div>
            </div>

            <ul className="space-y-hair">
              {media.libraryLoading ? (
                <li className="py-base text-xs text-ink-muted">{t("dashboard:loading")}</li>
              ) : media.libraryItems.length === 0 ? (
                <li className="py-base text-xs text-ink-muted">{t("dashboard:mediaFooterLibraryEmpty")}</li>
              ) : (
                media.libraryItems.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center gap-base rounded-tile px-base py-snug text-xs text-ink-primary hover:bg-white/5"
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 truncate text-left"
                      onClick={() => {
                        void media.playLibraryItem(item).then((r) => {
                          if (!r.ok && r.error) setErr(r.error);
                          else setErr(null);
                        });
                      }}
                    >
                      {libraryItemLabel(item, t("dashboard:mediaUntitledTrack"))}
                      <span className="ml-tight text-meta uppercase text-ink-muted">
                        {item.source_kind === "external_link"
                          ? t("dashboard:mediaFooterFilterRadio")
                          : item.source_kind === "upload"
                            ? t("dashboard:mediaFooterFilterSongs")
                            : item.source_kind === "embed"
                              ? t("dashboard:mediaFooterFilterEmbed")
                              : item.source_kind}
                      </span>
                    </button>
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      disabled={busy}
                      className="shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        void runAdd(async () => {
                          const result = await media.deleteLibraryItem(item);
                          return result;
                        });
                      }}
                    >
                      {t("dashboard:delete")}
                    </Button>
                  </li>
                ))
              )}
            </ul>
          </>
        )}

        {err ? <p className="text-meta text-red-300">{err}</p> : null}
      </div>
    </div>
  );
}
