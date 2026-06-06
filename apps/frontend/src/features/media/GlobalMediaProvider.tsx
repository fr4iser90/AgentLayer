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
import { mediaIdFromRef, useMediaStreamUrl } from "../dashboard/media/useMediaStreamUrl";
import {
  itemId,
  nextQueueItem,
  prevQueueItem,
  resolveNowItem,
  type MediaQueueItem,
  type MediaQueueState,
  type MediaSessionBinding,
} from "./mediaTypes";

type QueuePatchFn = (partial: Partial<MediaQueueState>) => void;

export type GlobalMediaContextValue = {
  active: boolean;
  paused: boolean;
  nowItem: MediaQueueItem | null;
  queue: MediaQueueState;
  binding: MediaSessionBinding | null;
  uploadMediaId: string | null;
  embedUrl: string | null;
  streamLoading: boolean;
  playFromDashboard: (
    item: MediaQueueItem,
    queue: MediaQueueState,
    binding: MediaSessionBinding,
    patchQueue: QueuePatchFn
  ) => void;
  syncDashboardQueue: (
    queue: MediaQueueState,
    binding: MediaSessionBinding,
    patchQueue: QueuePatchFn
  ) => void;
  togglePause: () => void;
  playNext: () => void;
  playPrev: () => void;
  stop: () => void;
  isPlayingItem: (item: MediaQueueItem) => boolean;
};

const GlobalMediaContext = createContext<GlobalMediaContextValue | null>(null);

function embedForItem(item: MediaQueueItem | null): string | null {
  if (!item || item.source_kind !== "embed") return null;
  const url = item.external_url?.trim();
  if (!url) return null;
  return embedUrlAllowed(url) ? url : null;
}

function externalStreamForItem(item: MediaQueueItem | null): string | null {
  if (!item || item.source_kind !== "external_link") return null;
  const url = item.external_url?.trim();
  return url || null;
}

function uploadIdForItem(item: MediaQueueItem | null): string | null {
  if (!item || item.source_kind !== "upload") return null;
  return mediaIdFromRef(item.ref);
}

function GlobalMediaEngine(props: {
  children: ReactNode;
  enabled: boolean;
}) {
  const { children, enabled } = props;
  const [queue, setQueue] = useState<MediaQueueState>({
    now_playing_id: null,
    items: [],
    shuffle: false,
    repeat: "off",
  });
  const [binding, setBinding] = useState<MediaSessionBinding | null>(null);
  const [paused, setPaused] = useState(false);
  const [active, setActive] = useState(false);
  const patchRef = useRef<QueuePatchFn | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const nowItem = useMemo(() => resolveNowItem(queue), [queue]);
  const uploadMediaId = enabled && active ? uploadIdForItem(nowItem) : null;
  const embedUrl = enabled && active ? embedForItem(nowItem) : null;
  const directStreamUrl = enabled && active ? externalStreamForItem(nowItem) : null;
  const blobStreamUrl = useMediaStreamUrl(uploadMediaId);
  const audioSrc = blobStreamUrl || directStreamUrl;
  const streamLoading = Boolean(uploadMediaId && !blobStreamUrl);

  const playItemInternal = useCallback(
    (item: MediaQueueItem, nextQueue: MediaQueueState, patchQueue: QueuePatchFn) => {
      const id = itemId(item);
      patchRef.current = patchQueue;
      setQueue({ ...nextQueue, now_playing_id: id });
      setActive(true);
      setPaused(false);
    },
    []
  );

  const playFromDashboard = useCallback(
    (
      item: MediaQueueItem,
      nextQueue: MediaQueueState,
      nextBinding: MediaSessionBinding,
      patchQueue: QueuePatchFn
    ) => {
      setBinding(nextBinding);
      playItemInternal(item, { ...nextQueue, now_playing_id: itemId(item) }, patchQueue);
      patchQueue({ now_playing_id: itemId(item) });
    },
    [playItemInternal]
  );

  const syncDashboardQueue = useCallback(
    (nextQueue: MediaQueueState, nextBinding: MediaSessionBinding, patchQueue: QueuePatchFn) => {
      patchRef.current = patchQueue;
      setBinding(nextBinding);
      setQueue(nextQueue);
    },
    []
  );

  const togglePause = useCallback(() => {
    const audio = audioRef.current;
    if (audioSrc && audio) {
      if (audio.paused) {
        void audio.play();
        setPaused(false);
      } else {
        audio.pause();
        setPaused(true);
      }
      return;
    }
    setPaused((p) => !p);
  }, [audioSrc]);

  const advance = useCallback(
    (direction: "next" | "prev") => {
      const currentId = queue.now_playing_id;
      const target =
        direction === "next"
          ? nextQueueItem(queue, currentId)
          : prevQueueItem(queue, currentId);
      if (!target) {
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
      audio.removeAttribute("src");
    }
    setActive(false);
    setPaused(true);
    patchRef.current = null;
    setBinding(null);
    setQueue({ now_playing_id: null, items: [], shuffle: false, repeat: "off" });
  }, []);

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
    if (!audio || !audioSrc) return;
    if (audio.src !== audioSrc) {
      audio.src = audioSrc;
    }
    if (!paused) {
      void audio.play().catch(() => setPaused(true));
    }
  }, [audioSrc, paused]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || audioSrc) return;
    audio.pause();
    audio.removeAttribute("src");
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
    if (!enabled) stop();
  }, [enabled, stop]);

  const value = useMemo<GlobalMediaContextValue>(
    () => ({
      active,
      paused,
      nowItem,
      queue,
      binding,
      uploadMediaId,
      embedUrl,
      streamLoading,
      playFromDashboard,
      syncDashboardQueue,
      togglePause,
      playNext,
      playPrev,
      stop,
      isPlayingItem,
    }),
    [
      active,
      paused,
      nowItem,
      queue,
      binding,
      uploadMediaId,
      embedUrl,
      streamLoading,
      playFromDashboard,
      syncDashboardQueue,
      togglePause,
      playNext,
      playPrev,
      stop,
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
