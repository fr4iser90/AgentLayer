import { useCallback, useEffect, useRef, useState } from "react";

type Options = {
  enabled: boolean;
  onUtterance: (blob: Blob) => void | Promise<void>;
  silenceMs?: number;
  speechThreshold?: number;
};

/**
 * Simple mic VAD: start recording when loud enough, end after silence.
 */
export function useVoiceHandsFree(options: Options) {
  const { enabled, onUtterance, silenceMs = 1200, speechThreshold = 0.018 } = options;
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const recordingRef = useRef(false);
  const lastVoiceRef = useRef(0);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stopTracks = () => {
    if (streamRef.current) {
      for (const t of streamRef.current.getTracks()) t.stop();
      streamRef.current = null;
    }
  };

  const stopRecorder = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
    recorderRef.current = null;
    recordingRef.current = false;
  }, []);

  const startRecording = useCallback(() => {
    const stream = streamRef.current;
    if (!stream || recordingRef.current) return;
    chunksRef.current = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const rec = new MediaRecorder(stream, { mimeType: mime });
    recorderRef.current = rec;
    rec.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
      chunksRef.current = [];
      if (blob.size > 0) void onUtterance(blob);
    };
    rec.start(200);
    recordingRef.current = true;
  }, [onUtterance]);

  const tick = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser || !enabled) return;
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    const now = performance.now();
    if (rms >= speechThreshold) {
      lastVoiceRef.current = now;
      if (!recordingRef.current) startRecording();
    } else if (recordingRef.current && now - lastVoiceRef.current > silenceMs) {
      stopRecorder();
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [enabled, silenceMs, speechThreshold, startRecording, stopRecorder]);

  useEffect(() => {
    if (!enabled) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      stopRecorder();
      stopTracks();
      setListening(false);
      return;
    }

    let cancelled = false;
    void (async () => {
      setError(null);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          for (const t of stream.getTracks()) t.stop();
          return;
        }
        streamRef.current = stream;
        const ctx = new AudioContext();
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        src.connect(analyser);
        analyserRef.current = analyser;
        setListening(true);
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Microphone unavailable");
      }
    })();

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      stopRecorder();
      stopTracks();
      setListening(false);
    };
  }, [enabled, stopRecorder, tick]);

  return { listening, error };
}
