import { useCallback, useRef } from "react";
import { apiFetch } from "../../lib/api";
import type { AuthContextValue } from "../../auth/AuthContext";

// Unicode Extended_Pictographic — covers emoji + ZWJ sequences (flags, skin tones, …).
const EMOJI_RE =
  /\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?)*/gu;

function stripMarkdownForSpeech(text: string): string {
  return text
    .replace(EMOJI_RE, " ")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`]+`/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[#*_~>|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function useVoicePlayback(auth: AuthContextValue | null) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);

  const stop = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  }, []);

  const speakBrowser = useCallback((text: string, language?: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return false;
    const u = new SpeechSynthesisUtterance(text);
    if (language) u.lang = language;
    utterRef.current = u;
    window.speechSynthesis.speak(u);
    return true;
  }, []);

  const speakServer = useCallback(
    async (text: string) => {
      if (!auth?.accessToken) return false;
      const res = await apiFetch("/v1/voice/tts", auth, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return false;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
      return true;
    },
    [auth]
  );

  const speak = useCallback(
    async (raw: string, opts?: { language?: string; preferServer?: boolean }) => {
      const text = stripMarkdownForSpeech(raw);
      if (!text) return;
      stop();
      if (opts?.preferServer) {
        const ok = await speakServer(text);
        if (ok) return;
      }
      if (!speakBrowser(text, opts?.language)) {
        await speakServer(text);
      }
    },
    [speakBrowser, speakServer, stop]
  );

  return { speak, stop };
}
