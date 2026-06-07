import { useCallback, useRef, useState } from "react";

export function useVoiceCapture() {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stopTracks = (rec: MediaRecorder | null) => {
    const stream = rec?.stream;
    if (stream) {
      for (const t of stream.getTracks()) t.stop();
    }
  };

  const start = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const rec = new MediaRecorder(stream, { mimeType: mime });
      recorderRef.current = rec;
      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      rec.start(200);
      setRecording(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Microphone unavailable");
      setRecording(false);
    }
  }, []);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") {
      setRecording(false);
      return null;
    }
    return new Promise((resolve) => {
      rec.onstop = () => {
        stopTracks(rec);
        recorderRef.current = null;
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        chunksRef.current = [];
        resolve(blob.size > 0 ? blob : null);
      };
      rec.stop();
    });
  }, []);

  const cancel = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      rec.onstop = () => {
        stopTracks(rec);
        recorderRef.current = null;
        chunksRef.current = [];
        setRecording(false);
      };
      rec.stop();
    } else {
      setRecording(false);
    }
  }, []);

  return { recording, error, start, stop, cancel };
}
