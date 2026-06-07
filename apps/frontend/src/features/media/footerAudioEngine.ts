import Hls from "hls.js";
import { mediaLog, mediaLogAudioError, mediaWarn } from "./mediaPlaybackLog";

export function isHlsStreamUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return lower.includes(".m3u8") || lower.includes("/hls/");
}

export type FooterAudioSession = {
  destroy: () => void;
};

export function attachFooterAudio(
  audio: HTMLAudioElement,
  src: string,
  onFatalError: () => void
): FooterAudioSession {
  let hls: Hls | null = null;
  const hlsUrl = isHlsStreamUrl(src);

  mediaLog("attach", {
    src,
    hlsUrl,
    hlsJsSupported: Hls.isSupported(),
    nativeHls: audio.canPlayType("application/vnd.apple.mpegurl"),
  });

  const onAudioError = () => mediaLogAudioError(audio, "attachFooterAudio");

  audio.addEventListener("error", onAudioError);

  const destroy = () => {
    audio.removeEventListener("error", onAudioError);
    if (hls) {
      hls.destroy();
      hls = null;
    }
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    mediaLog("destroy session");
  };

  if (hlsUrl) {
    if (Hls.isSupported()) {
      mediaLog("using hls.js");
      hls = new Hls({ enableWorker: true });
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        mediaLog("hls manifest parsed", { levels: hls?.levels?.length ?? 0 });
      });
      hls.on(Hls.Events.ERROR, (_, data) => {
        mediaWarn("hls error", {
          type: data.type,
          details: data.details,
          fatal: data.fatal,
          url: data.url ?? null,
          response: data.response?.code ?? null,
        });
        if (data.fatal) onFatalError();
      });
      hls.loadSource(src);
      hls.attachMedia(audio);
    } else if (audio.canPlayType("application/vnd.apple.mpegurl")) {
      mediaLog("using native HLS (Safari)");
      audio.src = src;
      audio.load();
    } else {
      mediaWarn("HLS not supported in this browser");
      onFatalError();
    }
  } else {
    mediaLog("using direct audio src");
    audio.src = src;
    audio.load();
  }

  return { destroy };
}
