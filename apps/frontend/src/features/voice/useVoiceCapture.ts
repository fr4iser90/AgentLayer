import { useCallback, useRef, useState } from "react";

const MIN_RECORDING_MS = 500;
const MIN_BLOB_BYTES = 800;

export type VoiceCaptureStopResult =
  | { ok: true; blob: Blob }
  | { ok: false; reason: "recording_too_short" | "no_audio" | "not_recording" | "mic_unavailable" };

export function useVoiceCapture() {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const startGenerationRef = useRef(0);
  const [recording, setRecording] = useState(false);

  const stopTracks = (stream: MediaStream | null | undefined) => {
    if (stream) {
      for (const t of stream.getTracks()) t.stop();
    }
  };

  const start = useCallback(async (): Promise<VoiceCaptureStopResult | null> => {
    const gen = ++startGenerationRef.current;
    chunksRef.current = [];
    startedAtRef.current = 0;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (gen !== startGenerationRef.current) {
        stopTracks(stream);
        return null;
      }
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const rec = new MediaRecorder(stream, { mimeType: mime });
      recorderRef.current = rec;
      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      rec.start();
      startedAtRef.current = Date.now();
      setRecording(true);
      return null;
    } catch {
      setRecording(false);
      recorderRef.current = null;
      return { ok: false, reason: "mic_unavailable" };
    }
  }, []);

  const stop = useCallback(async (): Promise<VoiceCaptureStopResult> => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") {
      setRecording(false);
      return { ok: false, reason: "not_recording" };
    }
    return new Promise((resolve) => {
      rec.onstop = () => {
        const elapsed = Date.now() - (startedAtRef.current || Date.now());
        stopTracks(rec.stream);
        recorderRef.current = null;
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        chunksRef.current = [];
        startedAtRef.current = 0;
        if (elapsed < MIN_RECORDING_MS || blob.size < MIN_BLOB_BYTES) {
          resolve({ ok: false, reason: "recording_too_short" });
          return;
        }
        if (blob.size === 0) {
          resolve({ ok: false, reason: "no_audio" });
          return;
        }
        resolve({ ok: true, blob });
      };
      if (rec.state === "recording") {
        try {
          rec.requestData();
        } catch {
          /* optional */
        }
      }
      rec.stop();
    });
  }, []);

  const cancel = useCallback(() => {
    startGenerationRef.current += 1;
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      rec.onstop = () => {
        stopTracks(rec.stream);
        recorderRef.current = null;
        chunksRef.current = [];
        startedAtRef.current = 0;
        setRecording(false);
      };
      rec.stop();
    } else {
      setRecording(false);
      recorderRef.current = null;
      chunksRef.current = [];
      startedAtRef.current = 0;
    }
  }, []);

  return { recording, start, stop, cancel };
};
