import { useVoiceCapture } from "./useVoiceCapture";

type Props = {
  disabled?: boolean;
  busy?: boolean;
  title: string;
  ariaLabel: string;
  onTranscript: (text: string) => void | Promise<void>;
  onError?: (message: string) => void;
  transcribe: (blob: Blob) => Promise<string>;
};

export function VoiceMicButton({
  disabled,
  busy,
  title,
  ariaLabel,
  onTranscript,
  onError,
  transcribe,
}: Props) {
  const { recording, start, stop, cancel } = useVoiceCapture();

  const handlePointerDown = async () => {
    if (disabled || busy || recording) return;
    await start();
  };

  const handlePointerUp = async () => {
    if (!recording) return;
    const blob = await stop();
    if (!blob) return;
    try {
      const transcript = await transcribe(blob);
      await onTranscript(transcript);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <button
      type="button"
      disabled={disabled || busy}
      className={`rounded-lg border p-2 transition-colors disabled:opacity-40 ${
        recording
          ? "border-rose-500/60 bg-rose-950/40 text-rose-100"
          : "border-white/10 bg-black/20 text-surface-muted hover:bg-white/5 hover:text-neutral-200"
      }`}
      title={title}
      aria-label={ariaLabel}
      aria-pressed={recording}
      onPointerDown={(e) => {
        e.preventDefault();
        void handlePointerDown();
      }}
      onPointerUp={() => void handlePointerUp()}
      onPointerLeave={() => {
        if (recording) void cancel();
      }}
      onPointerCancel={() => cancel()}
    >
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
        aria-hidden
      >
        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" x2="12" y1="19" y2="22" />
      </svg>
    </button>
  );
}
