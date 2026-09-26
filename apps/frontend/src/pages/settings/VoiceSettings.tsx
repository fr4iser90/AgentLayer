import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  fetchVoiceStatus,
  saveVoicePrefs,
  type VoicePrefs,
  type VoiceStatus,
} from "../../features/voice/voiceApi";
import { Select, TextInput } from "../../ui/Field";
import { Button } from "../../ui/Button";

const defaultPrefs: VoicePrefs = {
  input_enabled: true,
  output_enabled: false,
  language: "de",
  voice_id: null,
  mode_web: "push_to_talk",
  mode_telegram: "text_only",
  mode_discord: "text_only",
  edit_transcript_before_send: true,
};

export function VoiceSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [prefs, setPrefs] = useState<VoicePrefs>(defaultPrefs);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await fetchVoiceStatus(auth);
      setStatus(s);
      if (s?.prefs) setPrefs({ ...defaultPrefs, ...s.prefs });
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await saveVoicePrefs(auth, prefs);
      setMsg(t("settings:voiceSaved"));
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-ink-muted">{t("settings:voiceLoading")}</p>;
  }

  const disabledGlobally = !status?.operator_enabled || !status?.api_configured;

  return (
    <div className="mx-auto max-w-page">
      <h1 className="text-xl font-semibold text-ink-primary">{t("settings:voiceTitle")}</h1>
      <p className="mt-base text-sm text-ink-muted">{t("settings:voiceIntro")}</p>
      {disabledGlobally ? (
        <p className="mt-wide rounded-card border border-warning/30 bg-warning-subtle px-soft py-base text-sm text-badge-warning">
          {t("settings:voiceDisabledOperator")}
        </p>
      ) : null}
      {msg ? <p className="mt-soft text-sm text-ink-secondary">{msg}</p> : null}

      <div className="mt-broad space-y-wide rounded-sheet border border-line bg-card p-roomy">
        <label className="flex items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            checked={prefs.input_enabled}
            onChange={(e) => setPrefs((p) => ({ ...p, input_enabled: e.target.checked }))}
          />
          {t("settings:voiceInputEnabled")}
        </label>
        <label className="flex items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            checked={prefs.output_enabled}
            onChange={(e) => setPrefs((p) => ({ ...p, output_enabled: e.target.checked }))}
          />
          {t("settings:voiceOutputEnabled")}
        </label>
        <label className="flex items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            checked={prefs.edit_transcript_before_send}
            onChange={(e) =>
              setPrefs((p) => ({ ...p, edit_transcript_before_send: e.target.checked }))
            }
          />
          {t("settings:voiceEditTranscript")}
        </label>
        <label className="block text-xs text-ink-muted">
          {t("settings:voiceModeWeb")}
          <Select
            className="mt-tight max-w-controlWide"
            value={prefs.mode_web}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_web: e.target.value }))}
          >
            <option value="push_to_talk">{t("settings:voiceModePushToTalk")}</option>
            <option value="toggle">{t("settings:voiceModeToggle")}</option>
            <option value="hands_free">{t("settings:voiceModeHandsFree")}</option>
            <option value="realtime">{t("settings:voiceModeRealtime")}</option>
          </Select>
        </label>
        <label className="block text-xs text-ink-muted">
          {t("settings:voiceLanguage")}
          <TextInput
            className="mt-tight max-w-control"
            value={prefs.language}
            onChange={(e) => setPrefs((p) => ({ ...p, language: e.target.value }))}
            placeholder={t("settings:voiceLanguagePlaceholder")}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          {t("settings:voiceTtsVoice")}
          <TextInput
            className="mt-tight max-w-control"
            value={prefs.voice_id ?? ""}
            onChange={(e) =>
              setPrefs((p) => ({ ...p, voice_id: e.target.value.trim() || null }))
            }
            placeholder={t("settings:voiceTtsVoicePlaceholder")}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          {t("settings:voiceModeTelegram")}
          <Select
            className="mt-tight max-w-controlWide"
            value={prefs.mode_telegram}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_telegram: e.target.value }))}
          >
            <option value="text_only">{t("settings:voiceModeTextOnly")}</option>
            <option value="voice_reply">{t("settings:voiceModeVoiceOnly")}</option>
            <option value="voice_both">{t("settings:voiceModeBoth")}</option>
          </Select>
        </label>
        <label className="block text-xs text-ink-muted">
          {t("settings:voiceModeDiscord")}
          <Select
            className="mt-tight max-w-controlWide"
            value={prefs.mode_discord}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_discord: e.target.value }))}
          >
            <option value="text_only">{t("settings:voiceModeTextOnly")}</option>
            <option value="voice_reply">{t("settings:voiceModeVoiceOnly")}</option>
            <option value="voice_both">{t("settings:voiceModeBoth")}</option>
          </Select>
        </label>
        <Button
          variant="primary"
          size="lg"
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="px-wide py-base text-sm"
        >
          {t("settings:voiceSave")}
        </Button>
      </div>
    </div>
  );
}
