import { agentChatWsUrl } from "./agentChatWsCore";
import { createLiveTurnStore, type LiveTurnStore } from "./useAgentLiveTurn";

export type ActiveAgentTurn = {
  threadId: string;
  userMsgId: string;
  startedAtMs: number;
  streamEnabled: boolean;
};

type FinishCallback = () => void;

const SESSION_STORAGE_KEY = "agentlayer:active-agent-turn";

class AgentChatSessionImpl {
  readonly liveTurn: LiveTurnStore = createLiveTurnStore();
  private ws: WebSocket | null = null;
  private accessToken: string | null = null;
  private messageHandler: ((ev: MessageEvent) => void) | null = null;
  private finishCallback: FinishCallback | null = null;
  private activeTurn: ActiveAgentTurn | null = null;
  private listeners = new Set<() => void>();
  private closingIntentionally = false;
  private pageMounted = false;

  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  };

  private notify = (): void => {
    for (const listener of this.listeners) listener();
  };

  getActiveTurn = (): ActiveAgentTurn | null => this.activeTurn;

  isPageMounted = (): boolean => this.pageMounted;

  isTurnInProgress = (): boolean => this.activeTurn != null;

  setAccessToken = (token: string | null): void => {
    this.accessToken = token;
    if (!token) this.closeSocket();
  };

  setPageMounted = (mounted: boolean): void => {
    this.pageMounted = mounted;
    this.notify();
  };

  beginTurn = (turn: ActiveAgentTurn): void => {
    this.activeTurn = turn;
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(turn));
    } catch {
      /* ignore quota / private mode */
    }
    this.notify();
  };

  endTurn = (): void => {
    this.activeTurn = null;
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    this.notify();
  };

  setMessageHandler = (handler: ((ev: MessageEvent) => void) | null): void => {
    this.messageHandler = handler;
  };

  setFinishCallback = (fn: FinishCallback | null): void => {
    this.finishCallback = fn;
  };

  getSocket = (): WebSocket | null => this.ws;

  ensureSocket = (): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const tok = this.accessToken;
      if (!tok) {
        reject(new Error("Not signed in"));
        return;
      }
      const existing = this.ws;
      if (existing?.readyState === WebSocket.OPEN) {
        resolve(existing);
        return;
      }
      if (existing) {
        this.closingIntentionally = true;
        existing.close();
        this.ws = null;
      }
      this.closingIntentionally = false;
      const ws = new WebSocket(agentChatWsUrl(tok));
      ws.onopen = () => {
        this.ws = ws;
        ws.onmessage = (ev) => this.messageHandler?.(ev);
        resolve(ws);
      };
      ws.onerror = () => reject(new Error("WebSocket failed"));
      ws.onclose = () => {
        if (this.ws === ws) this.ws = null;
        if (!this.closingIntentionally && this.activeTurn) {
          this.finishCallback?.();
        }
      };
    });
  };

  sendCancel = (): void => {
    const socket = this.ws;
    if (socket?.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* ignore */
      }
    }
  };

  closeSocket = (): void => {
    this.closingIntentionally = true;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.closingIntentionally = false;
    this.finishCallback = null;
    this.endTurn();
    this.liveTurn.resetAfterCommit();
  };
}

let singleton: AgentChatSessionImpl | null = null;

export function getAgentChatSession(): AgentChatSessionImpl {
  if (!singleton) singleton = new AgentChatSessionImpl();
  return singleton;
}
