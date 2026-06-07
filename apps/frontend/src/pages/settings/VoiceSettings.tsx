import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  fetchVoiceStatus,
  saveVoicePrefs,
  type VoicePrefs,
  type VoiceStatus,
} from "../../features/voice/voiceApi";

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
    return <p className="text-sm text-surface-muted">{t("settings:voiceLoading")}</p>;
  }

  const disabledGlobally = !status?.operator_enabled || !status?.api_configured;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-white">{t("settings:voiceTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("settings:voiceIntro")}</p>
      {disabledGlobally ? (
        <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
          {t("settings:voiceDisabledOperator")}
        </p>
      ) : null}
      {msg ? <p className="mt-3 text-sm text-neutral-300">{msg}</p> : null}

      <div className="mt-6 space-y-4 rounded-xl border border-surface-border bg-surface-raised/80 p-5">
        <label className="flex items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            checked={prefs.input_enabled}
            onChange={(e) => setPrefs((p) => ({ ...p, input_enabled: e.target.checked }))}
          />
          {t("settings:voiceInputEnabled")}
        </label>
        <label className="flex items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            checked={prefs.output_enabled}
            onChange={(e) => setPrefs((p) => ({ ...p, output_enabled: e.target.checked }))}
          />
          {t("settings:voiceOutputEnabled")}
        </label>
        <label className="flex items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            checked={prefs.edit_transcript_before_send}
            onChange={(e) =>
              setPrefs((p) => ({ ...p, edit_transcript_before_send: e.target.checked }))
            }
          />
          {t("settings:voiceEditTranscript")}
        </label>
        <label className="block text-xs text-surface-muted">
          {t("settings:voiceModeWeb")}
          <select
            className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={prefs.mode_web}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_web: e.target.value }))}
          >
            <option value="push_to_talk">{t("settings:voiceModePushToTalk")}</option>
            <option value="hands_free">{t("settings:voiceModeHandsFree")}</option>
            <option value="realtime">{t("settings:voiceModeRealtime")}</option>
          </select>
        </label>
        <label className="block text-xs text-surface-muted">
          {t("settings:voiceLanguage")}
          <input
            className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={prefs.language}
            onChange={(e) => setPrefs((p) => ({ ...p, language: e.target.value }))}
            placeholder={t("settings:voiceLanguagePlaceholder")}
          />
        </label>
        <label className="block text-xs text-surface-muted">
          {t("settings:voiceTtsVoice")}
          <input
            className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={prefs.voice_id ?? ""}
            onChange={(e) =>
              setPrefs((p) => ({ ...p, voice_id: e.target.value.trim() || null }))
            }
            placeholder={t("settings:voiceTtsVoicePlaceholder")}
          />
        </label>
        <label className="block text-xs text-surface-muted">
          {t("settings:voiceModeTelegram")}
          <select
            className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={prefs.mode_telegram}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_telegram: e.target.value }))}
          >
            <option value="text_only">{t("settings:voiceModeTextOnly")}</option>
            <option value="voice_reply">{t("settings:voiceModeVoiceOnly")}</option>
            <option value="voice_both">{t("settings:voiceModeBoth")}</option>
          </select>
        </label>
        <label className="block text-xs text-surface-muted">
          {t("settings:voiceModeDiscord")}
          <select
            className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={prefs.mode_discord}
            onChange={(e) => setPrefs((p) => ({ ...p, mode_discord: e.target.value }))}
          >
            <option value="text_only">{t("settings:voiceModeTextOnly")}</option>
            <option value="voice_reply">{t("settings:voiceModeVoiceOnly")}</option>
            <option value="voice_both">{t("settings:voiceModeBoth")}</option>
          </select>
        </label>
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {t("settings:voiceSave")}
        </button>
      </div>
    </div>
  );
}
