import { useEffect, useRef, useSyncExternalStore } from "react";
import {
  appendTimelineEntry,
  type AgentTimelineEntry,
} from "./agentLogStorage";

export type LiveLogAppend = Omit<AgentTimelineEntry, "id" | "kind" | "text"> & {
  id?: string;
};

export type LiveTurnStore = {
  subscribeStream: (cb: () => void) => () => void;
  subscribeReasoningStream: (cb: () => void) => () => void;
  subscribeLog: (cb: () => void) => () => void;
  getStreamText: () => string;
  getStreamReasoningText: () => string;
  getAgentLog: () => AgentTimelineEntry[];
  isActive: () => boolean;
  beginTurn: (initialLog?: AgentTimelineEntry[]) => void;
  endTurn: () => void;
  resetAfterCommit: () => void;
  appendStreamDelta: (delta: string) => void;
  appendReasoningStreamDelta: (delta: string) => void;
  appendStreamSeparator: () => void;
  appendLogLine: (kind: string, text: string, extras?: LiveLogAppend) => void;
  takeAgentLogSnapshot: () => AgentTimelineEntry[];
};

export function createLiveTurnStore(): LiveTurnStore {
  let streamText = "";
  let streamReasoningText = "";
  let agentLog: AgentTimelineEntry[] = [];
  let active = false;

  const streamListeners = new Set<() => void>();
  const reasoningStreamListeners = new Set<() => void>();
  const logListeners = new Set<() => void>();
  let streamRaf: number | null = null;
  let reasoningStreamRaf: number | null = null;
  let logRaf: number | null = null;

  const cancelRaf = () => {
    if (streamRaf != null) {
      cancelAnimationFrame(streamRaf);
      streamRaf = null;
    }
    if (reasoningStreamRaf != null) {
      cancelAnimationFrame(reasoningStreamRaf);
      reasoningStreamRaf = null;
    }
    if (logRaf != null) {
      cancelAnimationFrame(logRaf);
      logRaf = null;
    }
  };

  const notifyStream = () => {
    for (const l of streamListeners) l();
  };

  const notifyReasoningStream = () => {
    for (const l of reasoningStreamListeners) l();
  };

  const notifyLog = () => {
    for (const l of logListeners) l();
  };

  const scheduleStreamFlush = () => {
    if (streamRaf != null) return;
    streamRaf = requestAnimationFrame(() => {
      streamRaf = null;
      notifyStream();
    });
  };

  const scheduleReasoningStreamFlush = () => {
    if (reasoningStreamRaf != null) return;
    reasoningStreamRaf = requestAnimationFrame(() => {
      reasoningStreamRaf = null;
      notifyReasoningStream();
    });
  };

  const scheduleLogFlush = () => {
    if (logRaf != null) return;
    logRaf = requestAnimationFrame(() => {
      logRaf = null;
      notifyLog();
    });
  };

  return {
    subscribeStream: (cb) => {
      streamListeners.add(cb);
      return () => streamListeners.delete(cb);
    },
    subscribeReasoningStream: (cb) => {
      reasoningStreamListeners.add(cb);
      return () => reasoningStreamListeners.delete(cb);
    },
    subscribeLog: (cb) => {
      logListeners.add(cb);
      return () => logListeners.delete(cb);
    },
    getStreamText: () => streamText,
    getStreamReasoningText: () => streamReasoningText,
    getAgentLog: () => agentLog,
    isActive: () => active,
    beginTurn: (initialLog: AgentTimelineEntry[] = []) => {
      cancelRaf();
      active = true;
      streamText = "";
      streamReasoningText = "";
      agentLog = [...initialLog];
      notifyStream();
      notifyReasoningStream();
      notifyLog();
    },
    endTurn: () => {
      cancelRaf();
      active = false;
      streamText = "";
      streamReasoningText = "";
      notifyStream();
      notifyReasoningStream();
    },
    resetAfterCommit: () => {
      cancelRaf();
      active = false;
      streamText = "";
      streamReasoningText = "";
      agentLog = [];
      notifyStream();
      notifyReasoningStream();
      notifyLog();
    },
    appendStreamDelta: (delta: string) => {
      if (!delta) return;
      streamText += delta;
      if (!streamText.trim()) return;
      scheduleStreamFlush();
    },
    appendReasoningStreamDelta: (delta: string) => {
      if (!delta) return;
      streamReasoningText += delta;
      if (!streamReasoningText.trim()) return;
      scheduleReasoningStreamFlush();
    },
    appendStreamSeparator: () => {
      streamText += "\n\n";
      scheduleStreamFlush();
    },
    appendLogLine: (kind: string, text: string, extras?: LiveLogAppend) => {
      agentLog = appendTimelineEntry(agentLog, { kind, text, ...extras });
      scheduleLogFlush();
    },
    takeAgentLogSnapshot: () => [...agentLog],
  };
}

/** Stable store instance for one chat session (mount once in ChatPage). */
export function useAgentLiveTurn(): LiveTurnStore {
  const storeRef = useRef<LiveTurnStore | null>(null);
  if (!storeRef.current) {
    storeRef.current = createLiveTurnStore();
  }
  const store = storeRef.current;

  useEffect(() => () => store.resetAfterCommit(), [store]);

  return store;
}

/** Subscribe to RAF-batched stream text (in-flight assistant body only). */
export function useAgentStreamText(store: LiveTurnStore): string {
  return useSyncExternalStore(store.subscribeStream, store.getStreamText, () => "");
}

/** Subscribe to RAF-batched reasoning stream text (in-flight assistant turn). */
export function useAgentStreamReasoning(store: LiveTurnStore): string {
  return useSyncExternalStore(
    store.subscribeReasoningStream,
    store.getStreamReasoningText,
    () => ""
  );
}

/** Subscribe to RAF-batched live timeline (activity panel + in-flight turn cards). */
export function useAgentLiveLog(store: LiveTurnStore): AgentTimelineEntry[] {
  return useSyncExternalStore(store.subscribeLog, store.getAgentLog, () => []);
}
