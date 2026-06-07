const TAG = "[media-playback]";

export function mediaLog(message: string, data?: Record<string, unknown>): void {
  if (data) console.info(TAG, message, data);
  else console.info(TAG, message);
}

export function mediaWarn(message: string, data?: Record<string, unknown>): void {
  if (data) console.warn(TAG, message, data);
  else console.warn(TAG, message);
}

export function mediaLogAudioError(audio: HTMLAudioElement, context: string): void {
  const err = audio.error;
  mediaWarn(`${context}: audio element error`, {
    code: err?.code ?? null,
    message: err?.message ?? null,
    src: audio.src || null,
    currentSrc: audio.currentSrc || null,
    readyState: audio.readyState,
    networkState: audio.networkState,
  });
}
