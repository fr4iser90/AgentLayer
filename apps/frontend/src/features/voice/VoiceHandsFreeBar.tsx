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
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-950/30 px-3 py-2 text-xs">
      <button
        type="button"
        onClick={onToggle}
        className={`rounded-md px-3 py-1.5 font-medium ${
          active
            ? "bg-violet-600 text-white hover:bg-violet-500"
            : "border border-white/15 text-violet-100 hover:bg-white/5"
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
