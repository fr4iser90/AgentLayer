import { apiFetch } from "../../lib/api";
import type { AuthContextValue } from "../../auth/AuthContext";

export type VoicePrefs = {
  input_enabled: boolean;
  output_enabled: boolean;
  language: string;
  voice_id: string | null;
  mode_web: string;
  mode_telegram: string;
  mode_discord: string;
  edit_transcript_before_send: boolean;
};

export type VoiceStatus = {
  ok: boolean;
  operator_enabled: boolean;
  api_configured: boolean;
  stt_configured?: boolean;
  tts_configured?: boolean;
  effective_enabled: boolean;
  input_web: boolean;
  output_web: boolean;
  realtime_web?: boolean;
  prefs: VoicePrefs;
};

export async function fetchVoiceStatus(auth: AuthContextValue): Promise<VoiceStatus | null> {
  const res = await apiFetch("/v1/voice/status", auth);
  if (!res.ok) return null;
  return (await res.json()) as VoiceStatus;
}

export async function transcribeVoiceBlob(
  auth: AuthContextValue,
  blob: Blob,
  filename = "recording.webm"
): Promise<string> {
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await apiFetch("/v1/voice/stt", auth, { method: "POST", body: form });
  const data = (await res.json()) as { ok?: boolean; transcript?: string; detail?: string };
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "STT failed");
  }
  const t = (data.transcript || "").trim();
  if (!t) throw new Error("Empty transcript");
  return t;
}

export async function saveVoicePrefs(
  auth: AuthContextValue,
  patch: Partial<VoicePrefs>
): Promise<void> {
  const res = await apiFetch("/v1/user/voice", auth, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      typeof (data as { detail?: string }).detail === "string"
        ? (data as { detail: string }).detail
        : "Save failed"
    );
  }
}
