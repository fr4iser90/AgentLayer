import type { GlobalMediaContextValue } from "./GlobalMediaProvider";

/** Start footer mini-player from ``agent.media_play`` or ``tool_done.media_play`` WS payload. */
export function applyMediaPlayFromWs(
  gm: GlobalMediaContextValue | null,
  raw: Record<string, unknown>
): void {
  if (!gm || raw.dashboard_id == null || raw.queue_path == null) return;
  gm.playFromAgentEnqueue({
    dashboardId: String(raw.dashboard_id),
    queuePath: String(raw.queue_path),
    queue:
      raw.queue ??
      ({
        now_playing_id: raw.now_playing_id != null ? String(raw.now_playing_id) : null,
        items: raw.item && typeof raw.item === "object" ? [raw.item] : [],
        shuffle: false,
        repeat: "off",
      } as const),
  });
}
