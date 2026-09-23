import { useTranslation } from "react-i18next";

type Props = {
  active: boolean;
  listening: boolean;
  busy: boolean;
  onToggle: () => void;
  error?: string | null;
};

export function VoiceHandsFreeBar({ active, listening, busy, onToggle, error }: Props) {
  const { t } = useTranslation(["chat"]);
  return (
    <div className="mb-base flex flex-wrap items-center gap-base rounded-card border border-violet-500/30 bg-violet-950/30 px-soft py-base text-xs">
      <button
        type="button"
        onClick={onToggle}
        className={`rounded-tile px-soft py-snug font-medium ${
          active
            ? "bg-violet-600 text-ink-on-fill hover:bg-violet-500"
            : "border border-line-strong text-violet-100 hover:bg-white/5"
        }`}
      >
        {active ? t("chat:voiceHandsFreeStop") : t("chat:voiceHandsFreeStart")}
      </button>
      <span className="text-violet-100/90">
        {busy
          ? t("chat:voiceHandsFreeBusy")
          : active && listening
            ? t("chat:voiceHandsFreeListening")
            : t("chat:voiceHandsFreeHint")}
      </span>
      {error ? <span className="text-rose-300">{error}</span> : null}
    </div>
  );
}
