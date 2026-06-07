import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import {
  fetchVoiceStatus,
  saveVoicePrefs,
  type VoicePrefs,
  type VoiceStatus,
} from "./voiceApi";

type Props = {
  auth: AuthContextValue;
  voiceStatus: VoiceStatus | null;
  onVoiceStatusChange: (next: VoiceStatus | null) => void;
};

export function ChatComposerVoiceControls({ auth, voiceStatus, onVoiceStatusChange }: Props) {
  const { t } = useTranslation(["chat"]);
  const [saving, setSaving] = useState(false);

  const operatorOn = Boolean(voiceStatus?.operator_enabled);
  const sttOk = Boolean(voiceStatus?.stt_configured);
  const ttsOk = Boolean(voiceStatus?.tts_configured);
  const anyConfigured = sttOk || ttsOk;

  const patchPrefs = async (patch: Partial<VoicePrefs>) => {
    if (!auth.accessToken || saving) return;
    setSaving(true);
    try {
      await saveVoicePrefs(auth, patch);
      const next = await fetchVoiceStatus(auth);
      onVoiceStatusChange(next);
    } finally {
      setSaving(false);
    }
  };

  if (!voiceStatus) {
    return (
      <div className="w-full">
        <p className="text-[10px] leading-snug text-surface-muted">{t("chat:voiceComposerLoading")}</p>
      </div>
    );
  }

  if (!operatorOn || !anyConfigured) {
    return (
      <div className="w-full rounded-lg border border-amber-500/20 bg-amber-950/20 px-2.5 py-2">
        <p className="text-[10px] leading-snug text-amber-100/90">{t("chat:voiceComposerDisabled")}</p>
        <Link
          to="/settings/voice"
          className="mt-1 inline-block text-[10px] text-sky-400/90 hover:text-sky-300 hover:underline"
        >
          {t("chat:voiceComposerSettingsLink")}
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">
          {t("chat:voiceComposerTitle")}
        </span>
        <Link
          to="/settings/voice"
          className="shrink-0 text-[10px] text-sky-400/80 hover:text-sky-300 hover:underline"
        >
          {t("chat:voiceComposerSettingsLink")}
        </Link>
      </div>
      <label
        className={`flex cursor-pointer items-center gap-2 text-[10px] font-medium uppercase tracking-wide ${
          ttsOk ? "text-surface-muted" : "text-neutral-500"
        }`}
        title={ttsOk ? t("chat:voiceComposerReadAloudHint") : t("chat:voiceComposerTtsOff")}
      >
        <input
          type="checkbox"
          className="rounded border-surface-border bg-[#1a1a1a] text-sky-500"
          checked={voiceStatus.prefs.output_enabled}
          disabled={!ttsOk || saving}
          onChange={(e) => void patchPrefs({ output_enabled: e.target.checked })}
        />
        <span>{t("chat:voiceComposerReadAloud")}</span>
      </label>
      <p className="pl-6 text-[10px] leading-snug text-surface-muted">
        {ttsOk ? t("chat:voiceComposerReadAloudHint") : t("chat:voiceComposerTtsOff")}
      </p>
      <label
        className={`flex cursor-pointer items-center gap-2 text-[10px] font-medium uppercase tracking-wide ${
          sttOk ? "text-surface-muted" : "text-neutral-500"
        }`}
        title={sttOk ? t("chat:voiceComposerInputHint") : t("chat:voiceComposerSttOff")}
      >
        <input
          type="checkbox"
          className="rounded border-surface-border bg-[#1a1a1a] text-sky-500"
          checked={voiceStatus.prefs.input_enabled}
          disabled={!sttOk || saving}
          onChange={(e) => void patchPrefs({ input_enabled: e.target.checked })}
        />
        <span>{t("chat:voiceComposerInput")}</span>
      </label>
      <p className="pl-6 text-[10px] leading-snug text-surface-muted">
        {sttOk ? t("chat:voiceComposerInputHint") : t("chat:voiceComposerSttOff")}
      </p>
      {sttOk &&
      voiceStatus.prefs.input_enabled &&
      (voiceStatus.prefs.mode_web === "push_to_talk" ||
        voiceStatus.prefs.mode_web === "toggle") ? (
        <label className="block text-[10px] text-surface-muted">
          {t("chat:voiceComposerMicMode")}
          <select
            className="mt-1 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
            value={
              voiceStatus.prefs.mode_web === "toggle" ? "toggle" : "push_to_talk"
            }
            disabled={saving}
            onChange={(e) => {
              const v = e.target.value;
              void patchPrefs({
                mode_web: v === "toggle" ? "toggle" : "push_to_talk",
              });
            }}
          >
            <option value="push_to_talk">{t("chat:voiceComposerMicHold")}</option>
            <option value="toggle">{t("chat:voiceComposerMicToggle")}</option>
          </select>
          <span className="mt-1 block leading-snug">{t("chat:voiceComposerMicModeHint")}</span>
        </label>
      ) : null}
    </div>
  );
}
