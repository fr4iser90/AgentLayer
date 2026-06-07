const STORAGE_KEY = "agentlayer:media-volume";

export function readStoredMediaVolume(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null) return 1;
    const v = Number(raw);
    if (!Number.isFinite(v)) return 1;
    return Math.min(1, Math.max(0, v));
  } catch {
    return 1;
  }
}

export function writeStoredMediaVolume(volume: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(Math.min(1, Math.max(0, volume))));
  } catch {
    /* ignore quota / private mode */
  }
}
