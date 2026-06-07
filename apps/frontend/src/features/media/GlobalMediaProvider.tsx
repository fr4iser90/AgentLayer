import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { embedUrlAllowed } from "../dashboard/EmbedBlock";
import { embedIframeSrc } from "./mediaEmbedSrc";
import { mediaCanPlay, mediaPlaysAudio } from "./mediaPlayerPlayback";
import { getPath } from "../dashboard/dashboardDataPaths";
import { mediaIdFromRef } from "../dashboard/media/useMediaStreamUrl";
import { mediaPlayerAudioSrc } from "./mediaStreamSrc";
import { attachFooterAudio } from "./footerAudioEngine";
import { mediaLog, mediaLogAudioError, mediaWarn } from "./mediaPlaybackLog";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import {
  loadQueueForBinding,
  persistQueueForBinding,
  resolveMediaSessionBinding,
  writeStoredBinding,
} from "./mediaDashboardSession";
import {
  fetchMediaLibraryItems,
  queueItemFromLibrary,
  type MediaLibraryFilter,
  type MediaLibraryItem,
  deleteMediaLibraryItem,
} from "./mediaLibraryApi";
import { readStoredMediaVolume, writeStoredMediaVolume } from "./mediaVolumePrefs";
import {
  itemId,
  nextQueueItem,
  prevQueueItem,
  readQueue,
  resolveNowItem,
  type MediaQueueItem,
  type MediaQueueState,
  type MediaSessionBinding,
} from "./mediaTypes";

type QueuePatchFn = (partial: Partial<MediaQueueState>) => void;

export type GlobalMediaContextValue = {
  libraryEnabled: boolean;
  volume: number;
  setVolume: (volume: number) => void;
  active: boolean;
  paused: boolean;
  nowItem: MediaQueueItem | null;
  queue: MediaQueueState;
  binding: MediaSessionBinding | null;
  libraryItems: MediaLibraryItem[];
  libraryLoading: boolean;
  libraryFilter: MediaLibraryFilter;
  setLibraryFilter: (filter: MediaLibraryFilter) => void;
  refreshLibrary: () => Promise<void>;
  uploadMediaId: string | null;
  embedUrl: string | null;
  streamLoading: boolean;
  playbackError: string | null;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  playFromDashboard: (
    item: MediaQueueItem,
    queue: MediaQueueState,
    binding: MediaSessionBinding,
    patchQueue: QueuePatchFn
  ) => void;
  playFromAgentEnqueue: (payload: {
    dashboardId: string;
    queuePath: string;
    queue: unknown;
    dashboardTitle?: string;
  }) => void;
  syncDashboardQueue: (
    queue: MediaQueueState,
    binding: MediaSessionBinding,
    patchQueue: QueuePatchFn
  ) => void;
  playQueueItem: (item: MediaQueueItem) => void;
  playLibraryItem: (item: MediaLibraryItem) => Promise<{ ok: boolean; error?: string }>;
  deleteLibraryItem: (item: MediaLibraryItem) => Promise<{ ok: boolean; error?: string }>;
  removeFromQueue: (index: number) => void;
  resumePlayback: () => void;
  togglePause: () => void;
  playNext: () => void;
  playPrev: () => void;
  stop: () => void;
  setRepeat: (mode: MediaQueueState["repeat"]) => void;
  toggleShuffle: () => void;
  isPlayingItem: (item: MediaQueueItem) => boolean;
};

const GlobalMediaContext = createContext<GlobalMediaContextValue | null>(null);

function embedForItem(item: MediaQueueItem | null, autoplay = false): string | null {
  if (!item || item.source_kind !== "embed") return null;
  const url = item.external_url?.trim();
  if (!url) return null;
  return embedIframeSrc(url, { autoplay }) ?? (embedUrlAllowed(url) ? url : null);
}

function uploadIdForItem(item: MediaQueueItem | null): string | null {
  if (!item || !mediaPlaysAudio(item)) return null;
  return mediaIdFromRef(item.ref);
}

function upsertQueueItem(queue: MediaQueueState, item: MediaQueueItem): MediaQueueState {
  const id = itemId(item);
  const items = [...queue.items];
  const idx = id != null ? items.findIndex((it) => itemId(it) === id) : -1;
  if (idx >= 0) items[idx] = { ...items[idx], ...item };
  else items.push(item);
  return { ...queue, items };
}

function GlobalMediaEngine(props: { children: ReactNode; enabled: boolean }) {
  const { children, enabled } = props;
  const auth = useAuth();
  const [queue, setQueue] = useState<MediaQueueState>({
    now_playing_id: null,
    items: [],
    shuffle: false,
    repeat: "off",
  });
  const [binding, setBinding] = useState<MediaSessionBinding | null>(null);
  const [paused, setPaused] = useState(false);
  const [active, setActive] = useState(false);
  const [libraryEnabled, setLibraryEnabled] = useState(false);
  const [libraryItems, setLibraryItems] = useState<MediaLibraryItem[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryFilter, setLibraryFilter] = useState<MediaLibraryFilter>("all");
  const [panelOpen, setPanelOpen] = useState(false);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [volume, setVolumeState] = useState(readStoredMediaVolume);
  const patchRef = useRef<QueuePatchFn | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioSessionRef = useRef<ReturnType<typeof attachFooterAudio> | null>(null);
  const bindingRef = useRef<MediaSessionBinding | null>(null);
  const queueRef = useRef(queue);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hydratedRef = useRef(false);

  bindingRef.current = binding;
  queueRef.current = queue;

  const setVolume = useCallback((next: number) => {
    const v = Math.min(1, Math.max(0, next));
    setVolumeState(v);
    writeStoredMediaVolume(v);
    const audio = audioRef.current;
    if (audio) audio.volume = v;
  }, []);

  const schedulePersist = useCallback(
    (nextQueue: MediaQueueState, nextBinding: MediaSessionBinding | null) => {
      if (!nextBinding) return;
      if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
      persistTimerRef.current = setTimeout(() => {
        void persistQueueForBinding(auth, nextBinding, nextQueue);
      }, 400);
    },
    [auth]
  );

  const applyBinding = useCallback((next: MediaSessionBinding | null) => {
    setBinding(next);
    bindingRef.current = next;
    writeStoredBinding(next);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLibraryEnabled(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetch("/v1/media/limits", auth);
        if (cancelled) return;
        if (!res.ok) {
          setLibraryEnabled(false);
          return;
        }
        const body = (await res.json()) as { library_enabled?: boolean };
        setLibraryEnabled(body.library_enabled === true);
      } catch {
        if (!cancelled) setLibraryEnabled(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, enabled]);

  const refreshLibrary = useCallback(async () => {
    if (!libraryEnabled) return;
    setLibraryLoading(true);
    try {
      const result = await fetchMediaLibraryItems(auth, libraryFilter);
      if (result.ok) setLibraryItems(result.items);
    } finally {
      setLibraryLoading(false);
    }
  }, [auth, libraryEnabled, libraryFilter]);

  useEffect(() => {
    if (!libraryEnabled) return;
    void refreshLibrary();
  }, [libraryEnabled, libraryFilter, refreshLibrary]);

  useEffect(() => {
    if (!libraryEnabled || hydratedRef.current) return;
    hydratedRef.current = true;
    void (async () => {
      const sessionBinding = await resolveMediaSessionBinding(auth);
      if (!sessionBinding) return;
      applyBinding(sessionBinding);
      const savedQueue = await loadQueueForBinding(auth, sessionBinding);
      setQueue(savedQueue);
      const item = resolveNowItem(savedQueue);
      if (item && mediaCanPlay(item) && savedQueue.now_playing_id) {
        setActive(true);
        setPaused(true);
      }
    })();
  }, [applyBinding, auth, libraryEnabled]);

  const nowItem = useMemo(() => resolveNowItem(queue), [queue]);
  const enrichedNowItem = useMemo(() => {
    if (!nowItem) return null;
    const id = mediaIdFromRef(nowItem.ref);
    if (!id) return nowItem;
    const lib = libraryItems.find((x) => x.id === id);
    if (!lib) return nowItem;
    return {
      ...nowItem,
      title: nowItem.title || lib.title,
      artist: nowItem.artist || lib.artist,
      source_kind:
        nowItem.source_kind ||
        (lib.source_kind === "upload" ||
        lib.source_kind === "embed" ||
        lib.source_kind === "external_link" ||
        lib.source_kind === "archive"
          ? lib.source_kind
          : undefined),
      external_url: nowItem.external_url?.trim() || lib.external_url?.trim() || undefined,
      stream_url: nowItem.stream_url?.trim() || lib.stream_url?.trim() || undefined,
    };
  }, [nowItem, libraryItems]);
  const audioItem =
    enabled && active && enrichedNowItem && mediaPlaysAudio(enrichedNowItem)
      ? enrichedNowItem
      : null;
  const embedUrl =
    enabled && active && !paused && enrichedNowItem?.source_kind === "embed"
      ? embedForItem(enrichedNowItem, true)
      : null;
  const audioSrc = mediaPlayerAudioSrc(audioItem, auth.accessToken);
  const streamLoading = Boolean(
    audioItem?.source_kind === "upload" && active && !audioSrc
  );
  const uploadMediaId =
    audioItem?.source_kind === "upload" ? mediaIdFromRef(audioItem.ref) : null;

  useEffect(() => {
    mediaLog("playback state", {
      active,
      paused,
      playbackError,
      audioSrc: audioSrc ?? null,
      footerRef: audioItem?.ref ?? null,
      source_kind: audioItem?.source_kind ?? null,
      external_url: audioItem?.external_url ?? null,
      stream_url: audioItem?.stream_url ?? null,
      enriched: enrichedNowItem !== nowItem,
    });
  }, [active, paused, playbackError, audioSrc, audioItem, enrichedNowItem, nowItem]);

  const playItemInternal = useCallback(
    (item: MediaQueueItem, nextQueue: MediaQueueState, patchQueue: QueuePatchFn) => {
      const id = itemId(item);
      patchRef.current = patchQueue;
      setQueue({ ...nextQueue, now_playing_id: id });
      setActive(true);
      setPaused(false);
      setPlaybackError(null);
      schedulePersist({ ...nextQueue, now_playing_id: id }, bindingRef.current);
    },
    [schedulePersist]
  );

  const playFromDashboard = useCallback(
    (
      item: MediaQueueItem,
      nextQueue: MediaQueueState,
      nextBinding: MediaSessionBinding,
      patchQueue: QueuePatchFn
    ) => {
      applyBinding(nextBinding);
      playItemInternal(item, { ...nextQueue, now_playing_id: itemId(item) }, patchQueue);
      patchQueue({ now_playing_id: itemId(item) });
    },
    [applyBinding, playItemInternal]
  );

  const playFromAgentEnqueue = useCallback(
    (payload: {
      dashboardId: string;
      queuePath: string;
      queue: unknown;
      dashboardTitle?: string;
    }) => {
      void (async () => {
        let nextQueue = readQueue(payload.queue);
        const dashId = payload.dashboardId.trim();
        const queuePath = payload.queuePath.trim();
        if (!dashId || !queuePath) return;

        if (!nextQueue.items.length) {
          try {
            const res = await apiFetch(`/v1/dashboards/${encodeURIComponent(dashId)}`, auth);
            if (res.ok) {
              const body = (await res.json()) as { dashboard?: { data?: Record<string, unknown> } };
              const data = body.dashboard?.data;
              if (data && typeof data === "object") {
                nextQueue = readQueue(getPath(data, queuePath));
              }
            }
          } catch {
            /* keep empty queue */
          }
        }

        const item = resolveNowItem(nextQueue);
        if (!item) return;
        const nextBinding: MediaSessionBinding = {
          dashboardId: dashId,
          dataPath: queuePath,
          dashboardTitle: payload.dashboardTitle?.trim() || undefined,
        };
        applyBinding(nextBinding);
        if (mediaCanPlay(item)) {
          playItemInternal(item, nextQueue, () => {});
        } else {
          setQueue(nextQueue);
          schedulePersist(nextQueue, nextBinding);
        }
      })();
    },
    [applyBinding, auth, playItemInternal, schedulePersist]
  );

  const syncDashboardQueue = useCallback(
    (nextQueue: MediaQueueState, nextBinding: MediaSessionBinding, patchQueue: QueuePatchFn) => {
      patchRef.current = patchQueue;
      applyBinding(nextBinding);
      setQueue(nextQueue);
    },
    [applyBinding]
  );

  const ensureBinding = useCallback(async (): Promise<MediaSessionBinding | null> => {
    if (bindingRef.current) return bindingRef.current;
    const b = await resolveMediaSessionBinding(auth);
    if (b) applyBinding(b);
    return b;
  }, [applyBinding, auth]);

  const playQueueItem = useCallback(
    (item: MediaQueueItem) => {
      if (!mediaCanPlay(item)) return;
      const id = itemId(item);
      const nextQueue = { ...queueRef.current, now_playing_id: id };
      playItemInternal(item, nextQueue, patchRef.current ?? (() => {}));
      patchRef.current?.({ now_playing_id: id });
    },
    [playItemInternal]
  );

  const playLibraryItem = useCallback(
    async (item: MediaLibraryItem): Promise<{ ok: boolean; error?: string }> => {
      const sessionBinding = await ensureBinding();
      if (!sessionBinding) {
        return { ok: false, error: "no_dashboard" };
      }
      const queueItem = queueItemFromLibrary(item);
      let nextQueue = upsertQueueItem(queueRef.current, queueItem);
      nextQueue = { ...nextQueue, now_playing_id: itemId(queueItem) };
      setQueue(nextQueue);
      schedulePersist(nextQueue, sessionBinding);
      playItemInternal(queueItem, nextQueue, patchRef.current ?? (() => {}));
      return { ok: true };
    },
    [ensureBinding, playItemInternal, schedulePersist]
  );

  const deleteLibraryItem = useCallback(
    async (item: MediaLibraryItem): Promise<{ ok: boolean; error?: string }> => {
      const result = await deleteMediaLibraryItem(auth, item.id);
      if (!result.ok) return { ok: false, error: result.error };

      setLibraryItems((prev) => prev.filter((x) => x.id !== item.id));

      const deletedId = item.id.trim();
      const cur = queueRef.current;
      const nextItems = cur.items.filter((it) => itemId(it) !== deletedId);
      const wasPlaying = cur.now_playing_id === deletedId && active;
      let nextNow = cur.now_playing_id;
      if (nextNow === deletedId) {
        nextNow = nextItems[0] ? itemId(nextItems[0]) : null;
      }
      const nextQueue: MediaQueueState = { ...cur, items: nextItems, now_playing_id: nextNow };
      setQueue(nextQueue);
      schedulePersist(nextQueue, bindingRef.current);

      if (wasPlaying) {
        if (nextItems[0] && mediaCanPlay(nextItems[0])) {
          playItemInternal(nextItems[0], nextQueue, patchRef.current ?? (() => {}));
        } else {
          setActive(false);
          setPaused(true);
          setPlaybackError(null);
        }
      }

      return { ok: true };
    },
    [active, auth, playItemInternal, schedulePersist]
  );

  const removeFromQueue = useCallback(
    (index: number) => {
      const cur = queueRef.current;
      const removed = cur.items[index];
      const nextItems = cur.items.filter((_, i) => i !== index);
      const removedId = removed ? itemId(removed) : null;
      let nextNow = cur.now_playing_id;
      if (removedId && cur.now_playing_id === removedId) {
        nextNow = nextItems[0] ? itemId(nextItems[0]) : null;
      }
      const nextQueue: MediaQueueState = { ...cur, items: nextItems, now_playing_id: nextNow };
      setQueue(nextQueue);
      schedulePersist(nextQueue, bindingRef.current);
      const playingId = cur.now_playing_id;
      if (removedId && playingId === removedId) {
        if (nextItems[0] && mediaCanPlay(nextItems[0])) {
          playItemInternal(nextItems[0], nextQueue, patchRef.current ?? (() => {}));
        } else {
          setActive(false);
          setPaused(true);
        }
      }
    },
    [playItemInternal, schedulePersist]
  );

  const resumePlayback = useCallback(() => {
    const item = resolveNowItem(queueRef.current);
    if (item && mediaCanPlay(item)) {
      playItemInternal(item, queueRef.current, patchRef.current ?? (() => {}));
      return;
    }
    const first = queueRef.current.items.find((it) => mediaCanPlay(it));
    if (first) playQueueItem(first);
  }, [playItemInternal, playQueueItem]);

  const togglePause = useCallback(() => {
    if (!active || !nowItem) {
      resumePlayback();
      return;
    }
    const audio = audioRef.current;
    if (audioSrc && audio) {
      if (audio.paused) {
        if (playbackError === "stream_error") {
          audioSessionRef.current?.destroy();
          const session = attachFooterAudio(audio, audioSrc, () => {
            mediaWarn("togglePause retry: stream_error");
            setPaused(true);
            setPlaybackError("stream_error");
          });
          audioSessionRef.current = session;
        }
        void audio.play()
          .then(() => {
            mediaLog("togglePause: play ok");
            setPaused(false);
            setPlaybackError(null);
          })
          .catch((e) => {
            mediaWarn("togglePause: play rejected", {
              name: e instanceof Error ? e.name : "unknown",
              message: e instanceof Error ? e.message : String(e),
            });
            mediaLogAudioError(audio, "togglePause play catch");
            setPaused(true);
            setPlaybackError("play_blocked");
          });
      } else {
        audio.pause();
        setPaused(true);
      }
      return;
    }
    setPaused((p) => !p);
  }, [active, audioSrc, nowItem, playbackError, resumePlayback]);

  const advance = useCallback(
    (direction: "next" | "prev") => {
      const currentId = queue.now_playing_id;
      const target =
        direction === "next"
          ? nextQueueItem(queue, currentId)
          : prevQueueItem(queue, currentId);
      if (!target || !mediaCanPlay(target)) {
        if (direction === "next" && queue.repeat !== "one") {
          setActive(false);
          setPaused(true);
        }
        return;
      }
      const id = itemId(target);
      playItemInternal(target, { ...queue, now_playing_id: id }, patchRef.current ?? (() => {}));
      patchRef.current?.({ now_playing_id: id });
    },
    [playItemInternal, queue]
  );

  const playNext = useCallback(() => advance("next"), [advance]);
  const playPrev = useCallback(() => advance("prev"), [advance]);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
    }
    setActive(false);
    setPaused(true);
  }, []);

  const setRepeat = useCallback(
    (mode: MediaQueueState["repeat"]) => {
      const nextQueue = { ...queueRef.current, repeat: mode };
      setQueue(nextQueue);
      schedulePersist(nextQueue, bindingRef.current);
    },
    [schedulePersist]
  );

  const toggleShuffle = useCallback(() => {
    const nextQueue = { ...queueRef.current, shuffle: !queueRef.current.shuffle };
    setQueue(nextQueue);
    schedulePersist(nextQueue, bindingRef.current);
  }, [schedulePersist]);

  const isPlayingItem = useCallback(
    (item: MediaQueueItem) => {
      if (!active || !nowItem) return false;
      const a = itemId(item);
      const b = itemId(nowItem);
      return a != null && b != null && a === b;
    },
    [active, nowItem]
  );

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !audioSrc) {
      audioSessionRef.current?.destroy();
      audioSessionRef.current = null;
      return;
    }
    audioSessionRef.current?.destroy();
    audio.volume = volume;
    const session = attachFooterAudio(audio, audioSrc, () => {
      mediaWarn("stream_error callback");
      mediaLogAudioError(audio, "onFatalError");
      setPaused(true);
      setPlaybackError("stream_error");
    });
    audioSessionRef.current = session;
    return () => {
      session.destroy();
      if (audioSessionRef.current === session) audioSessionRef.current = null;
    };
  }, [audioSrc, volume]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !audioSrc) return;
    if (paused) {
      audio.pause();
      return;
    }
    void audio.play().catch((e) => {
      mediaWarn("audio.play() rejected", {
        name: e instanceof Error ? e.name : "unknown",
        message: e instanceof Error ? e.message : String(e),
        audioSrc,
      });
      mediaLogAudioError(audio, "play() catch");
      setPaused(true);
      setPlaybackError("play_blocked");
    });
  }, [audioSrc, paused]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onPlaying = () => {
      mediaLog("audio playing");
      setPlaybackError(null);
    };
    audio.addEventListener("playing", onPlaying);
    return () => audio.removeEventListener("playing", onPlaying);
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || audioSrc) return;
    audioSessionRef.current?.destroy();
    audioSessionRef.current = null;
    audio.pause();
  }, [audioSrc]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onEnded = () => {
      if (queue.repeat === "one") {
        audio.currentTime = 0;
        void audio.play();
        return;
      }
      playNext();
    };
    audio.addEventListener("ended", onEnded);
    return () => audio.removeEventListener("ended", onEnded);
  }, [playNext, queue.repeat]);

  useEffect(() => {
    if (!enabled) {
      setActive(false);
      setQueue({ now_playing_id: null, items: [], shuffle: false, repeat: "off" });
      applyBinding(null);
      hydratedRef.current = false;
    }
  }, [applyBinding, enabled]);

  const value = useMemo<GlobalMediaContextValue>(
    () => ({
      libraryEnabled,
      volume,
      setVolume,
      active,
      paused,
      nowItem,
      queue,
      binding,
      libraryItems,
      libraryLoading,
      libraryFilter,
      setLibraryFilter,
      refreshLibrary,
      uploadMediaId,
      embedUrl,
      streamLoading,
      playbackError,
      panelOpen,
      setPanelOpen,
      playFromDashboard,
      playFromAgentEnqueue,
      syncDashboardQueue,
      playQueueItem,
      playLibraryItem,
      deleteLibraryItem,
      removeFromQueue,
      resumePlayback,
      togglePause,
      playNext,
      playPrev,
      stop,
      setRepeat,
      toggleShuffle,
      isPlayingItem,
    }),
    [
      libraryEnabled,
      volume,
      setVolume,
      active,
      paused,
      nowItem,
      queue,
      binding,
      libraryItems,
      libraryLoading,
      libraryFilter,
      refreshLibrary,
      uploadMediaId,
      embedUrl,
      streamLoading,
      playbackError,
      panelOpen,
      setPanelOpen,
      playFromDashboard,
      playFromAgentEnqueue,
      syncDashboardQueue,
      playQueueItem,
      playLibraryItem,
      deleteLibraryItem,
      removeFromQueue,
      resumePlayback,
      togglePause,
      playNext,
      playPrev,
      stop,
      setRepeat,
      toggleShuffle,
      isPlayingItem,
    ]
  );

  return (
    <GlobalMediaContext.Provider value={value}>
      {children}
      {enabled ? (
        <audio ref={audioRef} className="hidden" preload="auto">
          <track kind="captions" />
        </audio>
      ) : null}
    </GlobalMediaContext.Provider>
  );
}

export function GlobalMediaProvider(props: { children: ReactNode; enabled?: boolean }) {
  return <GlobalMediaEngine enabled={props.enabled ?? true}>{props.children}</GlobalMediaEngine>;
}

export function useGlobalMedia(): GlobalMediaContextValue {
  const ctx = useContext(GlobalMediaContext);
  if (!ctx) {
    throw new Error("useGlobalMedia requires GlobalMediaProvider");
  }
  return ctx;
}

export function useOptionalGlobalMedia(): GlobalMediaContextValue | null {
  return useContext(GlobalMediaContext);
}
