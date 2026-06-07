import type { PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { useVoiceCapture } from "./useVoiceCapture";

export type VoiceMicInteraction = "hold" | "toggle";

type Props = {
  disabled?: boolean;
  busy?: boolean;
  interaction?: VoiceMicInteraction;
  title?: string;
  ariaLabel?: string;
  onTranscript: (text: string) => void | Promise<void>;
  onError?: (message: string) => void;
  onTranscribeStart?: () => void;
  onTranscribeEnd?: () => void;
  transcribe: (blob: Blob) => Promise<string>;
};

export function VoiceMicButton({
  disabled,
  busy,
  interaction = "hold",
  title,
  ariaLabel,
  onTranscript,
  onError,
  onTranscribeStart,
  onTranscribeEnd,
  transcribe,
}: Props) {
  const { t } = useTranslation(["chat"]);
  const { recording, start, stop, cancel } = useVoiceCapture();

  const resolvedTitle =
    title ??
    (interaction === "toggle" ? t("chat:voiceMicToggleTitle") : t("chat:voiceMicTitle"));
  const resolvedAria =
    ariaLabel ??
    (interaction === "toggle" ? t("chat:voiceMicToggleAria") : t("chat:voiceMicAria"));

  const finishCapture = async () => {
    const captured = await stop();
    if (!captured.ok) {
      if (captured.reason === "recording_too_short" || captured.reason === "no_audio") {
        onError?.(t("chat:voiceMicTooShort"));
      }
      return;
    }
    onTranscribeStart?.();
    try {
      const transcript = await transcribe(captured.blob);
      await onTranscript(transcript);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : String(e));
    } finally {
      onTranscribeEnd?.();
    }
  };

  const beginCapture = async () => {
    if (disabled || busy || recording) return false;
    const started = await start();
    if (started && !started.ok && started.reason === "mic_unavailable") {
      onError?.(t("chat:voiceMicUnavailable"));
      return false;
    }
    return true;
  };

  const handleHoldPointerDown = async (e: PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    await beginCapture();
  };

  const handleHoldPointerUp = async () => {
    if (!recording) return;
    await finishCapture();
  };

  const handleToggleClick = async () => {
    if (disabled || busy) return;
    if (recording) {
      await finishCapture();
      return;
    }
    await beginCapture();
  };

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        disabled={disabled || busy}
        className={`relative rounded-lg border p-2 transition-colors disabled:opacity-40 ${
          recording
            ? "border-rose-500/70 bg-rose-950/50 text-rose-100 shadow-[0_0_12px_rgba(244,63,94,0.25)]"
            : "border-white/10 bg-black/20 text-surface-muted hover:bg-white/5 hover:text-neutral-200"
        }`}
        title={resolvedTitle}
        aria-label={recording ? `${resolvedAria} — ${t("chat:voiceMicRec")}` : resolvedAria}
        aria-pressed={recording}
        onClick={interaction === "toggle" ? () => void handleToggleClick() : undefined}
        onPointerDown={interaction === "hold" ? (e) => void handleHoldPointerDown(e) : undefined}
        onPointerUp={interaction === "hold" ? () => void handleHoldPointerUp() : undefined}
        onPointerLeave={
          interaction === "hold"
            ? () => {
                if (recording) void cancel();
              }
            : undefined
        }
        onPointerCancel={interaction === "hold" ? () => cancel() : undefined}
      >
        {recording ? (
          <>
            <span
              className="pointer-events-none absolute -inset-0.5 animate-pulse rounded-lg border border-rose-400/50"
              aria-hidden
            />
            <span
              className="pointer-events-none absolute -right-1 -top-1 z-10 flex items-center gap-0.5 rounded border border-rose-400/60 bg-rose-950 px-1 py-px text-[8px] font-bold uppercase leading-none tracking-wide text-rose-100 shadow-sm"
              aria-live="polite"
            >
              <span className="relative flex h-1.5 w-1.5 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-80" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-rose-400" />
              </span>
              {t("chat:voiceMicRec")}
            </span>
          </>
        ) : null}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="relative"
          aria-hidden
        >
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" x2="12" y1="19" y2="22" />
        </svg>
      </button>
    </div>
  );
}
