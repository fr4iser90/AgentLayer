import { useCallback, useEffect, useRef } from "react";
import {
  agentChatWsUrl,
  handleAgentWsMessage,
  type AgentToolDoneEvent,
  type AgentWsTurnCallbacks,
  type AgentWsTurnResult,
} from "./agentChatWsCore";
import { detectUserTimezone } from "../../lib/userTimezone";
import type { LiveTurnStore } from "./useAgentLiveTurn";

export type AgentChatTurnBody = Record<string, unknown>;

export type RunAgentChatTurnOpts = {
  body: AgentChatTurnBody;
  onToolDone?: (ev: AgentToolDoneEvent) => void;
  onMediaPlay?: (payload: Record<string, unknown>) => void;
  /** Fired once after ``slowHintMs`` while the turn is still running (no hard abort). */
  onSlow?: (elapsedMs: number) => void;
  slowHintMs?: number;
  streamEnabled?: boolean;
};

export type AgentChatTurnResult = AgentWsTurnResult;

/**
 * Persistent ``/ws/v1/chat`` connection — same lifecycle as ChatPage agent mode
 * (no per-turn hard timeout; reuses an open socket when possible).
 */
export function useAgentChatWs(options: {
  accessToken: string | null | undefined;
  liveTurn: LiveTurnStore;
  pausedStepLabel?: string;
}) {
  const { accessToken, liveTurn, pausedStepLabel } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef<(ev: MessageEvent) => void>(() => {});
  const toolStartTimesRef = useRef(new Map<string, number>());
  const cancelPendingRef = useRef(false);
  const turnActiveRef = useRef(false);

  const ensureAgentWs = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const tok = accessToken;
      if (!tok) {
        reject(new Error("Not signed in"));
        return;
      }
      const existing = wsRef.current;
      if (existing?.readyState === WebSocket.OPEN) {
        resolve(existing);
        return;
      }
      if (existing) {
        existing.close();
        wsRef.current = null;
      }
      const ws = new WebSocket(agentChatWsUrl(tok));
      ws.onopen = () => {
        wsRef.current = ws;
        ws.onmessage = (ev) => handlerRef.current(ev);
        resolve(ws);
      };
      ws.onerror = () => reject(new Error("WebSocket failed"));
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
      };
    });
  }, [accessToken]);

  const cancelTurn = useCallback(() => {
    if (!turnActiveRef.current) return;
    cancelPendingRef.current = true;
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* */
      }
    }
  }, []);

  const runTurn = useCallback(
    async (opts: RunAgentChatTurnOpts): Promise<AgentChatTurnResult> => {
      const {
        body,
        onToolDone,
        onMediaPlay,
        onSlow,
        slowHintMs = 90_000,
        streamEnabled = true,
      } = opts;

      let finished = false;
      let slowTimer: ReturnType<typeof setTimeout> | null = null;
      const started = Date.now();
      turnActiveRef.current = true;
      cancelPendingRef.current = false;
      toolStartTimesRef.current = new Map();

      const clearSlowTimer = () => {
        if (slowTimer != null) {
          clearTimeout(slowTimer);
          slowTimer = null;
        }
      };

      const callbacks: AgentWsTurnCallbacks = {
        onToolDone,
        onMediaPlay,
        streamEnabled,
      };

      return new Promise<AgentChatTurnResult>((resolve, reject) => {
        const turn = {
          isFinished: () => finished,
          markFinished: () => {
            finished = true;
            turnActiveRef.current = false;
            clearSlowTimer();
          },
          resolve: (result: AgentWsTurnResult) => {
            if (finished) return;
            turn.markFinished();
            resolve(result);
          },
          reject: (err: Error) => {
            if (finished) return;
            turn.markFinished();
            reject(err);
          },
        };

        slowTimer = setTimeout(() => {
          if (!finished) onSlow?.(Date.now() - started);
        }, Math.max(5_000, slowHintMs));

        handlerRef.current = (ev: MessageEvent) => {
          try {
            const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
            handleAgentWsMessage(msg, {
              liveTurn,
              toolStartTimes: toolStartTimesRef.current,
              turn,
              callbacks,
              pausedStepLabel,
            });
          } catch {
            turn.reject(new Error("Invalid WebSocket message"));
          }
        };

        void (async () => {
          try {
            const ws = await ensureAgentWs();
            const priorOnClose = ws.onclose;
            ws.onclose = (ev) => {
              priorOnClose?.call(ws, ev);
              if (!finished) {
                turn.reject(new Error("WebSocket closed"));
              }
            };
            if (cancelPendingRef.current) {
              turn.reject(new Error("Cancelled"));
              return;
            }
            ws.send(
              JSON.stringify({
                type: "chat",
                body,
                user_timezone_header: detectUserTimezone(),
              })
            );
          } catch (e) {
            turn.reject(e instanceof Error ? e : new Error(String(e)));
          }
        })();
      });
    },
    [ensureAgentWs, liveTurn, pausedStepLabel]
  );

  useEffect(() => {
    return () => {
      const ws = wsRef.current;
      if (ws) {
        ws.close();
        wsRef.current = null;
      }
    };
  }, []);

  return { runTurn, cancelTurn, ensureAgentWs };
}
