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
import { Select } from "../../ui/Field";

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
        <p className="text-meta leading-snug text-ink-muted">{t("chat:voiceComposerLoading")}</p>
      </div>
    );
  }

  if (!operatorOn || !anyConfigured) {
    return (
      <div className="w-full rounded-card border border-warning/20 bg-warning-subtle px-firm py-base">
        <p className="text-meta leading-snug text-badge-warning">{t("chat:voiceComposerDisabled")}</p>
        <Link
          to="/settings/voice"
          className="mt-tight inline-block text-meta text-accent hover:text-badge-accent hover:underline"
        >
          {t("chat:voiceComposerSettingsLink")}
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full space-y-base">
      <div className="flex items-center justify-between gap-base">
        <span className="text-meta font-medium uppercase tracking-wide text-ink-muted">
          {t("chat:voiceComposerTitle")}
        </span>
        <Link
          to="/settings/voice"
          className="shrink-0 text-meta text-accent hover:text-badge-accent hover:underline"
        >
          {t("chat:voiceComposerSettingsLink")}
        </Link>
      </div>
      <label
        className={`flex cursor-pointer items-center gap-base text-meta font-medium uppercase tracking-wide ${
          ttsOk ? "text-ink-muted" : "text-ink-muted"
        }`}
        title={ttsOk ? t("chat:voiceComposerReadAloudHint") : t("chat:voiceComposerTtsOff")}
      >
        <input
          type="checkbox"
          className="rounded-tile border-line bg-field text-accent"
          checked={voiceStatus.prefs.output_enabled}
          disabled={!ttsOk || saving}
          onChange={(e) => void patchPrefs({ output_enabled: e.target.checked })}
        />
        <span>{t("chat:voiceComposerReadAloud")}</span>
      </label>
      <p className="pl-broad text-meta leading-snug text-ink-muted">
        {ttsOk ? t("chat:voiceComposerReadAloudHint") : t("chat:voiceComposerTtsOff")}
      </p>
      <label
        className={`flex cursor-pointer items-center gap-base text-meta font-medium uppercase tracking-wide ${
          sttOk ? "text-ink-muted" : "text-ink-muted"
        }`}
        title={sttOk ? t("chat:voiceComposerInputHint") : t("chat:voiceComposerSttOff")}
      >
        <input
          type="checkbox"
          className="rounded-tile border-line bg-field text-accent"
          checked={voiceStatus.prefs.input_enabled}
          disabled={!sttOk || saving}
          onChange={(e) => void patchPrefs({ input_enabled: e.target.checked })}
        />
        <span>{t("chat:voiceComposerInput")}</span>
      </label>
      <p className="pl-broad text-meta leading-snug text-ink-muted">
        {sttOk ? t("chat:voiceComposerInputHint") : t("chat:voiceComposerSttOff")}
      </p>
      {sttOk &&
      voiceStatus.prefs.input_enabled &&
      (voiceStatus.prefs.mode_web === "push_to_talk" ||
        voiceStatus.prefs.mode_web === "toggle") ? (
        <label className="block text-meta text-ink-muted">
          {t("chat:voiceComposerMicMode")}
          <Select
            className="mt-tight"
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
          </Select>
          <span className="mt-tight block leading-snug">{t("chat:voiceComposerMicModeHint")}</span>
        </label>
      ) : null}
    </div>
  );
}
