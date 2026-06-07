import { useCallback, useRef, useState } from "react";
import { voiceRealtimeWsUrl, type VoiceRealtimeEvent } from "./voiceRealtimeWs";

export type VoiceRealtimeHandlers = {
  onTranscript?: (text: string) => void;
  onReplyText?: (text: string) => void;
  onError?: (detail: string) => void;
  onDone?: () => void;
};

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const res = reader.result;
      if (typeof res !== "string") {
        reject(new Error("read failed"));
        return;
      }
      const idx = res.indexOf(",");
      resolve(idx >= 0 ? res.slice(idx + 1) : res);
    };
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

export function useVoiceRealtime(accessToken: string | null | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<VoiceRealtimeHandlers>({});
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);

  const setHandlers = useCallback((h: VoiceRealtimeHandlers) => {
    handlersRef.current = h;
  }, []);

  const ensureWs = useCallback((): Promise<WebSocket> => {
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
      const ws = new WebSocket(voiceRealtimeWsUrl(tok));
      ws.onopen = () => {
        wsRef.current = ws;
        setConnected(true);
        resolve(ws);
      };
      ws.onerror = () => reject(new Error("Voice WebSocket failed"));
      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
          setConnected(false);
        }
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as VoiceRealtimeEvent;
          const h = handlersRef.current;
          if (msg.type === "voice.transcript" && msg.text) h.onTranscript?.(msg.text);
          if (msg.type === "voice.reply_text" && msg.text) h.onReplyText?.(msg.text);
          if (msg.type === "voice.error") {
            setBusy(false);
            h.onError?.(msg.detail || "Voice error");
          }
          if (msg.type === "voice.cancelled") setBusy(false);
          if (msg.type === "voice.audio" && msg.audio_b64) {
            const mime = msg.mime || "audio/mpeg";
            const bin = atob(msg.audio_b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
            const audio = new Audio(url);
            audio.onended = () => URL.revokeObjectURL(url);
            void audio.play();
          }
          if (msg.type === "voice.done") {
            setBusy(false);
            h.onDone?.();
          }
        } catch {
          handlersRef.current.onError?.("Invalid voice WS message");
        }
      };
    });
  }, [accessToken]);

  const sendUtterance = useCallback(
    async (blob: Blob, chatBody: Record<string, unknown>) => {
      setBusy(true);
      const ws = await ensureWs();
      const audio_b64 = await blobToBase64(blob);
      ws.send(
        JSON.stringify({
          type: "utterance",
          audio_b64,
          mime: blob.type || "audio/webm",
          chat_body: chatBody,
        })
      );
    },
    [ensureWs]
  );

  const cancel = useCallback(() => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "cancel" }));
    }
    setBusy(false);
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
  }, []);

  return { connected, busy, setHandlers, sendUtterance, cancel, disconnect, ensureWs };
}
