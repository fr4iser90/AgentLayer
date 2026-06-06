import type { Dispatch, SetStateAction } from "react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { useOptionalGlobalMedia } from "../media/GlobalMediaProvider";
import {
  itemId,
  itemLabel,
  readQueue,
  resolveNowItem,
  type MediaQueueItem,
  type MediaQueueState,
} from "../media/mediaTypes";
import { embedUrlAllowed } from "./EmbedBlock";
import { getPath, setPath } from "./dashboardDataPaths";
import { MEDIA_AUDIO_ACCEPT, addMediaEmbed, uploadMediaFile } from "./media/mediaUpload";
import { MediaSharePanel } from "./media/MediaSharePanel";
import { mediaIdFromRef, useMediaStreamUrl } from "./media/useMediaStreamUrl";

function LocalUploadPlayer(props: { mediaId: string }) {
  const { t } = useTranslation(["dashboard"]);
  const url = useMediaStreamUrl(props.mediaId);
  if (!url) {
    return <p className="text-xs text-surface-muted">{t("dashboard:mediaStreamLoading")}</p>;
  }
  return (
    <audio controls className="w-full" src={url}>
      <track kind="captions" />
    </audio>
  );
}

export type { MediaQueueItem } from "../media/mediaTypes";

export function MediaPlayerBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
  dashboardId?: string;
  dashboardTitle?: string;
}) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const globalMedia = useOptionalGlobalMedia();
  const { dp, data, setData, sectionTitle, readOnly, dashboardId, dashboardTitle } = props;
  const st = readQueue(dp ? getPath(data, dp) : undefined);
  const [embedUrl, setEmbedUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const patchQueue = useCallback(
    (partial: Partial<MediaQueueState>) => {
      setData((d) => {
        const cur = readQueue(dp ? getPath(d, dp) : undefined);
        return setPath(d, dp, { ...cur, ...partial } as unknown);
      });
    },
    [dp, setData]
  );

  const sessionBinding = useCallback(
    () =>
      dashboardId
        ? { dashboardId, dataPath: dp, dashboardTitle: dashboardTitle?.trim() || undefined }
        : null,
    [dashboardId, dp, dashboardTitle]
  );

  const startPlayback = useCallback(
    (item: MediaQueueItem, queue: MediaQueueState = st) => {
      const binding = sessionBinding();
      if (!binding || !globalMedia) {
        patchQueue({ now_playing_id: itemId(item) });
        return;
      }
      globalMedia.playFromDashboard(item, queue, binding, patchQueue);
    },
    [globalMedia, patchQueue, sessionBinding, st]
  );

  const nowItem = resolveNowItem(st);
  const nowMediaId = nowItem?.source_kind === "upload" ? mediaIdFromRef(nowItem.ref) : null;
  const nowExternalStream =
    nowItem?.source_kind === "external_link" && nowItem.external_url?.trim()
      ? nowItem.external_url.trim()
      : null;
  const nowEmbed =
    nowItem && (nowItem.source_kind === "embed" || nowItem.external_url) && nowItem.external_url
      ? embedUrlAllowed(nowItem.external_url)
        ? nowItem.external_url
        : null
      : null;
  const globalPlayingNow =
    globalMedia != null && nowItem != null && globalMedia.isPlayingItem(nowItem) && globalMedia.active;

  const addItem = (item: MediaQueueItem) => {
    const id = itemId(item);
    const nextItems = [...st.items, item];
    const nextNow = st.now_playing_id ?? id;
    patchQueue({ items: nextItems, now_playing_id: nextNow });
    if (!st.now_playing_id) startPlayback(item, { ...st, items: nextItems, now_playing_id: nextNow });
  };

  const onUpload = async (file: File) => {
    if (!dashboardId) {
      setErr(t("dashboard:dashboardSaveBeforeUpload"));
      return;
    }
    setUploading(true);
    setErr(null);
    const result = await uploadMediaFile(file, auth, { dashboardId }, t);
    setUploading(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    addItem({
      ref: result.item.media_ref,
      title: result.item.title || file.name,
      artist: result.item.artist || "",
      source_kind: "upload",
      stream_url: result.item.stream_url,
    });
  };

  const onAddEmbed = async () => {
    const url = embedUrl.trim();
    if (!url || !embedUrlAllowed(url)) {
      setErr(t("dashboard:embedUrlNotAllowed"));
      return;
    }
    if (!dashboardId) {
      setErr(t("dashboard:dashboardSaveBeforeUpload"));
      return;
    }
    setUploading(true);
    setErr(null);
    const result = await addMediaEmbed(url, auth, { dashboardId }, t);
    setUploading(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setEmbedUrl("");
    addItem({
      ref: result.item.media_ref,
      title: result.item.title || sectionTitle,
      artist: result.item.artist || "",
      source_kind: "embed",
      external_url: result.item.external_url || url,
    });
  };

  const playItem = (it: MediaQueueItem) => startPlayback(it);

  const removeAt = (idx: number) => {
    const next = st.items.filter((_, i) => i !== idx);
    const removed = st.items[idx];
    const removedId = removed ? itemId(removed) : null;
    const nextNow =
      removedId && st.now_playing_id === removedId ? (next[0] ? itemId(next[0]) : null) : st.now_playing_id;
    patchQueue({ items: next, now_playing_id: nextNow });
    if (removed && globalMedia?.isPlayingItem(removed)) {
      if (next[0]) startPlayback(next[0], { ...st, items: next, now_playing_id: itemId(next[0]) });
      else globalMedia.stop();
    }
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3 md:p-4">
      <h3 className="mb-3 text-sm font-medium text-white">{sectionTitle}</h3>

      <div className="mb-4 min-h-[4rem] rounded-lg border border-white/10 bg-black/40 p-3">
        {!nowItem ? (
          <p className="text-sm text-surface-muted">{t("dashboard:mediaQueueEmpty")}</p>
        ) : nowEmbed ? (
          <div className="aspect-video max-h-48 overflow-hidden rounded-md">
            <iframe title={itemLabel(nowItem, sectionTitle)} src={nowEmbed} className="h-full w-full border-0" />
          </div>
        ) : nowMediaId || nowExternalStream ? (
          globalMedia ? (
            <div className="space-y-2">
              <p className="text-sm text-white">{itemLabel(nowItem, t("dashboard:mediaUntitledTrack"))}</p>
              {nowExternalStream ? (
                <p className="text-xs text-surface-muted">{t("dashboard:mediaMiniPlayerStreamHint")}</p>
              ) : null}
              {globalPlayingNow ? (
                <p className="text-xs text-sky-200/90">{t("dashboard:mediaPlayingInFooter")}</p>
              ) : null}
              <button
                type="button"
                className="rounded-lg border border-sky-500/40 bg-sky-950/40 px-3 py-1.5 text-xs text-sky-100 hover:bg-sky-900/40"
                onClick={() => (globalPlayingNow ? globalMedia.togglePause() : startPlayback(nowItem))}
              >
                {globalPlayingNow && !globalMedia.paused
                  ? t("dashboard:mediaMiniPlayerPause")
                  : t("dashboard:mediaMiniPlayerPlay")}
              </button>
            </div>
          ) : nowMediaId ? (
            <LocalUploadPlayer mediaId={nowMediaId} />
          ) : (
            <audio controls className="w-full" src={nowExternalStream ?? undefined}>
              <track kind="captions" />
            </audio>
          )
        ) : (
          <p className="text-sm text-amber-200">{t("dashboard:mediaPlaybackUnavailable")}</p>
        )}
        {nowItem && nowEmbed ? (
          <p className="mt-2 text-xs text-surface-muted">{itemLabel(nowItem, sectionTitle)}</p>
        ) : null}
      </div>

      {!readOnly ? (
        <div className="dashboard-grid-no-drag mb-4 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-surface-border bg-black/30 px-3 py-1.5 text-xs text-white hover:bg-white/5 disabled:opacity-50"
              disabled={uploading || !dashboardId}
              onClick={() => fileRef.current?.click()}
            >
              {uploading ? t("dashboard:loading") : t("dashboard:mediaUploadTrack")}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={MEDIA_AUDIO_ACCEPT}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) void onUpload(f);
              }}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              type="url"
              className="min-w-[12rem] flex-1 rounded-lg border border-surface-border bg-black/40 px-3 py-2 font-mono text-xs text-neutral-100"
              placeholder={t("dashboard:embedUrlPlaceholder")}
              value={embedUrl}
              onChange={(e) => setEmbedUrl(e.target.value)}
            />
            <button
              type="button"
              className="rounded-lg border border-sky-500/40 bg-sky-950/40 px-3 py-2 text-xs text-sky-100 hover:bg-sky-900/40 disabled:opacity-50"
              disabled={uploading || !embedUrl.trim()}
              onClick={() => void onAddEmbed()}
            >
              {t("dashboard:mediaAddEmbed")}
            </button>
          </div>
          {err ? <p className="text-xs text-red-400">{err}</p> : null}
        </div>
      ) : null}

      {st.items.length > 0 ? (
        <ol className="space-y-1">
          {st.items.map((it, idx) => {
            const id = itemId(it);
            const active = id != null && id === (st.now_playing_id ?? itemId(st.items[0]));
            return (
              <li
                key={`${id ?? idx}-${idx}`}
                className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                  active ? "bg-sky-950/40 text-sky-100" : "text-neutral-200 hover:bg-white/5"
                }`}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left"
                  onClick={() => playItem(it)}
                  disabled={readOnly && !active}
                >
                  {itemLabel(it, t("dashboard:mediaUntitledTrack"))}
                </button>
                {!readOnly ? (
                  <button
                    type="button"
                    className="shrink-0 text-[10px] uppercase text-red-300 hover:text-red-200"
                    onClick={() => removeAt(idx)}
                  >
                    {t("dashboard:delete")}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : readOnly ? (
        <p className="text-sm text-surface-muted">{t("dashboard:mediaQueueEmptyReadOnly")}</p>
      ) : null}

      {!readOnly ? <MediaSharePanel /> : null}
    </section>
  );
}
