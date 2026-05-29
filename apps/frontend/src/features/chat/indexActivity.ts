import type { IndexRunMode } from "./chatThreadStorage";
import { indexRunCardTitle } from "./buildRunCards";

export type IndexActivityEvent =
  | {
      type: "start";
      mode: IndexRunMode;
      phase?: string;
    }
  | {
      type: "done";
      mode: IndexRunMode;
      failed?: boolean;
      error?: string;
      durationMs?: number;
      filesDone?: number;
      filesTotal?: number;
      phase?: string;
    };

export function indexActivityToTimeline(
  ev: IndexActivityEvent
): { kind: string; text: string; extras: Record<string, unknown> } {
  if (ev.type === "start") {
    return {
      kind: "index_start",
      text: indexRunCardTitle(ev.mode),
      extras: {
        indexMode: ev.mode,
        indexPhase: ev.phase,
        runStatus: "running",
      },
    };
  }
  const failed = ev.failed === true;
  return {
    kind: "index_done",
    text: failed
      ? (ev.error?.trim() || "Index failed").slice(0, 200)
      : indexRunCardTitle(ev.mode),
    extras: {
      indexMode: ev.mode,
      indexPhase: ev.phase,
      runStatus: failed ? "failed" : "done",
      durationMs: ev.durationMs,
      filesDone: ev.filesDone,
      filesTotal: ev.filesTotal,
    },
  };
}
