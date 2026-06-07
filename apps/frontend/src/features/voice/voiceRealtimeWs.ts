export function voiceRealtimeWsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/voice/realtime?token=${encodeURIComponent(token)}`;
}

export type VoiceRealtimeEvent =
  | { type: "voice.session"; ok?: boolean }
  | { type: "voice.transcript"; text: string }
  | { type: "voice.reply_text"; text: string }
  | { type: "voice.audio"; audio_b64: string; mime?: string }
  | { type: "voice.done" }
  | { type: "voice.error"; detail?: string }
  | { type: "voice.cancelled" }
  | { type: "pong" };
