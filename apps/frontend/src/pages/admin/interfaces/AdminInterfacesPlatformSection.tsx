import { AdminInterfacesLegalSection } from "./AdminInterfacesLegalSection";
import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import {
  envProviderPatternFromCleanupKeys,
  type OperatorEnvProviderPreview,
} from "../../../features/admin/operatorSettings/operatorSettingsTypes";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";

function ProviderModelSelect({
  id,
  value,
  models,
  loading,
  onChange,
  placeholder,
  loadingLabel,
}: {
  id: string;
  value: string;
  models: string[];
  loading?: boolean;
  onChange: (value: string) => void;
  placeholder: string;
  loadingLabel: string;
}) {
  const current = value.trim();
  const options = current && !models.includes(current) ? [current, ...models] : models;
  return (
    <select
      id={id}
      className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary disabled:opacity-50"
      value={current}
      disabled={loading || options.length === 0}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{loading ? loadingLabel : placeholder}</option>
      {options.map((model) => (
        <option key={model} value={model}>
          {model}
        </option>
      ))}
    </select>
  );
}

export function AdminInterfacesPlatformSection({ mode = "all" }: { mode?: "all" | "platform" | "voice" }) {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  const sttProviderId = s.voiceSttProviderId || s.voiceSttProviderIdEffective || "";
  const ttsProviderId = s.voiceTtsProviderId || s.voiceTtsProviderIdEffective || "";
  const sttModelsKey = s.operatorProviderModelKey("voice_stt", sttProviderId);
  const ttsModelsKey = s.operatorProviderModelKey("voice_tts", ttsProviderId);
  const sttModels = s.operatorProviderModelOptions[sttModelsKey] ?? [];
  const ttsModels = s.operatorProviderModelOptions[ttsModelsKey] ?? [];

  useEffect(() => {
    if (sttProviderId) void s.loadOperatorProviderModels("voice_stt", sttProviderId);
  }, [sttProviderId, s.loadOperatorProviderModels]);

  useEffect(() => {
    if (ttsProviderId) void s.loadOperatorProviderModels("voice_tts", ttsProviderId);
  }, [ttsProviderId, s.loadOperatorProviderModels]);

  if (s.loading) {
    return <p className="text-sm text-ink-muted">{t("admin:loading")}</p>;
  }
  const showPlatform = mode === "all" || mode === "platform";
  const showVoice = mode === "all" || mode === "voice";
  const voiceMetadata = s.operatorProviderKindMetadata.filter((metadata) =>
    ["stt", "tts"].includes(metadata.capability)
  );
  const voiceMetadataByKind = new Map(voiceMetadata.map((metadata) => [metadata.kind, metadata]));
  const voiceEnvPrefixPatterns = voiceMetadata
    .map((metadata) => metadata.env_prefix_pattern)
    .filter((prefix): prefix is string => !!prefix);
  const pendingVoiceEnvGroups = Object.values(s.envOperatorProviders)
    .flat()
    .filter((provider) => voiceMetadataByKind.has(provider.kind) && !provider.already_in_db)
    .reduce<Array<{ kind: string; prefix: string; providers: OperatorEnvProviderPreview[] }>>((groups, provider) => {
      const group = groups.find((item) => item.kind === provider.kind);
      if (group) {
        group.providers.push(provider);
        return groups;
      }
      groups.push({
        kind: provider.kind,
        prefix:
          voiceMetadataByKind.get(provider.kind)?.env_prefix_pattern ??
          envProviderPatternFromCleanupKeys(provider.cleanup_keys),
        providers: [provider],
      });
      return groups;
    }, []);
  return (
    <>
          {showPlatform ? (
          <>
          <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformAgentModeTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformAgentModeIntro")}</p>
            <p className="mt-base text-xs text-ink-muted">
              {t("admin:ifPlatformAgentModeEnvEffective", {
                env: s.agentModeEnv,
                effective: s.agentModeEffective,
              })}
            </p>
            <label className="mt-soft block text-xs text-ink-muted" htmlFor="agent-mode">
              {t("admin:ifPlatformAgentModeOverride")}
            </label>
            <select
              id="agent-mode"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
              value={s.agentMode}
              onChange={(e) => s.setAgentMode(e.target.value as "env" | "sandbox" | "host")}
            >
              <option value="env">{t("admin:ifPlatformAgentModeUseEnv")}</option>
              <option value="sandbox">{t("admin:ifPlatformAgentModeSandbox")}</option>
              <option value="host">{t("admin:ifPlatformAgentModeHost")}</option>
            </select>
          </section>
          <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformDashboardUploadsTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformUploadIntro")}</p>
            {s.uploadEffBytes != null ? (
              <p className="mt-base text-xs text-ink-muted">
                {t("admin:ifPlatformUploadEffective", {
                  bytes: s.uploadEffBytes,
                  mime: s.uploadEffMime.join(", ") || "—",
                })}
              </p>
            ) : null}
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="wu-mb">
              {t("admin:ifPlatformUploadMaxMb")}
            </label>
            <input
              id="wu-mb"
              type="number"
              min={1}
              max={512}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.uploadMaxMb}
              onChange={(e) => s.setUploadMaxMb(e.target.value)}
              placeholder={t("admin:ifPlatformUploadMbPlaceholder")}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="wu-mime">
              {t("admin:ifPlatformUploadMime")}
            </label>
            <input
              id="wu-mime"
              className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.uploadMime}
              onChange={(e) => s.setUploadMime(e.target.value)}
              placeholder={t("admin:ifPlatformMimePlaceholder")}
            />
          </section>

          <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformMediaTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformMediaIntro")}</p>
            {s.mediaEffUploadBytes != null ? (
              <p className="mt-base text-xs text-ink-muted">
                {t("admin:ifPlatformMediaEffective", {
                  bytes: s.mediaEffUploadBytes,
                  mime: s.mediaEffUploadMime.join(", ") || "—",
                  quotaMb: s.mediaEffDefaultQuotaMb ?? "—",
                })}
              </p>
            ) : null}
            <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.mediaLibraryEnabled}
                onChange={(e) => s.setMediaLibraryEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaLibraryEnabled")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.mediaUserUploadEnabled}
                onChange={(e) => s.setMediaUserUploadEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaUploadEnabled")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.mediaSharingEnabled}
                onChange={(e) => s.setMediaSharingEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaSharingEnabled")}
            </label>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="media-quota-mb">
              {t("admin:ifPlatformMediaDefaultQuotaMb")}
            </label>
            <input
              id="media-quota-mb"
              type="number"
              min={1}
              max={50000}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.mediaDefaultQuotaMb}
              onChange={(e) => s.setMediaDefaultQuotaMb(e.target.value)}
              placeholder={t("admin:ifPlatformMediaQuotaPlaceholder")}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="media-upload-mb">
              {t("admin:ifPlatformMediaUploadMaxMb")}
            </label>
            <input
              id="media-upload-mb"
              type="number"
              min={1}
              max={512}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.mediaUploadMaxMb}
              onChange={(e) => s.setMediaUploadMaxMb(e.target.value)}
              placeholder={t("admin:ifPlatformUploadMbPlaceholder")}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="media-mime">
              {t("admin:ifPlatformMediaUploadMime")}
            </label>
            <input
              id="media-mime"
              className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.mediaUploadMime}
              onChange={(e) => s.setMediaUploadMime(e.target.value)}
              placeholder={t("admin:ifPlatformMimePlaceholder")}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="media-embed-hosts">
              {t("admin:ifPlatformMediaEmbedHosts")}
            </label>
            <input
              id="media-embed-hosts"
              className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.mediaEmbedHosts}
              onChange={(e) => s.setMediaEmbedHosts(e.target.value)}
              placeholder={t("admin:ifPlatformMediaEmbedHostsPlaceholder")}
            />
          </section>

          <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformChatQuotaTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformChatQuotaIntro")}</p>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="chat-max-mb">
              {t("admin:ifPlatformChatMaxConversationMb")}
            </label>
            <input
              id="chat-max-mb"
              type="number"
              min={1}
              max={50000}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.chatMaxConversationMb}
              onChange={(e) => s.setChatMaxConversationMb(e.target.value)}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="chat-max-personal">
              {t("admin:ifPlatformChatMaxPersonalSessions")}
            </label>
            <input
              id="chat-max-personal"
              type="number"
              min={1}
              max={10000}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.chatMaxPersonalSessions}
              onChange={(e) => s.setChatMaxPersonalSessions(e.target.value)}
            />
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="chat-max-dashboard">
              {t("admin:ifPlatformChatMaxDashboardSessions")}
            </label>
            <input
              id="chat-max-dashboard"
              type="number"
              min={1}
              max={10000}
              className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
              value={s.chatMaxDashboardSessions}
              onChange={(e) => s.setChatMaxDashboardSessions(e.target.value)}
            />
            <p className="mt-soft text-xs text-ink-muted">{t("admin:ifPlatformChatQuotaWarnHint")}</p>
          </section>

          <AdminInterfacesLegalSection />

          </>
          ) : null}

          {showVoice ? (
          <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformVoiceTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformVoiceIntro")}</p>
            {pendingVoiceEnvGroups.length > 0 ? (
              <div className="mt-wide space-y-soft">
                {pendingVoiceEnvGroups.map(({ kind, prefix, providers }) => {
                  return (
                    <div key={kind} className="rounded-card border border-warning/25 bg-warning-subtle p-wide">
                      <div className="flex flex-col gap-soft sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-badge-warning">
                            {t("admin:envProviderFoundTitle", { count: providers.length })}
                          </h3>
                          <p className="mt-tight text-xs text-badge-warning">
                            {t("admin:envProviderFoundIntro", { prefix })}
                          </p>
                        </div>
                        <button
                          type="button"
                          disabled={s.envOperatorImporting === kind}
                          className="rounded-tile bg-warning px-soft py-snug text-sm font-medium text-black hover:bg-warning-hover disabled:opacity-50"
                          onClick={() => void s.importOperatorEnvProviders(kind)}
                        >
                          {s.envOperatorImporting === kind ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
                        </button>
                      </div>
                      <div className="mt-soft space-y-base">
                        {providers.map((p) => (
                          <details key={p.provider_id} className="rounded-tile border border-line bg-black/25 p-soft">
                            <summary className="cursor-pointer text-xs text-badge-warning">
                              <span className="font-mono">{p.provider_id}</span> · {p.label}
                              {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                            </summary>
                            <p className="mt-base break-all font-mono text-meta text-ink-muted">{p.base_url}</p>
                            <p className="mt-tight text-meta text-ink-secondary">
                              {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                            </p>
                            <ul className="mt-base grid gap-tight sm:grid-cols-2">
                              {p.cleanup_keys.map((key) => (
                                <li key={key} className="font-mono text-meta text-badge-warning">{key}</li>
                              ))}
                            </ul>
                          </details>
                        ))}
                      </div>
                      {s.envOperatorCleanupNotes[kind] ? (
                        <p className="mt-soft text-xs text-badge-warning">{s.envOperatorCleanupNotes[kind]}</p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : null}
            <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.voiceEnabled}
                onChange={(e) => s.setVoiceEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceEnabled")}
            </label>
            <div className="mt-wide rounded-card border border-line bg-black/15 p-wide">
              <div className="flex flex-wrap items-center justify-between gap-base">
                <span className="text-xs font-medium text-ink-muted">{t("admin:ifPlatformVoiceEndpoint")}</span>
                {s.voiceApiBaseSource === "env" ? (
                  <span className="text-xs text-badge-warning">{t("admin:ifPlatformVoiceBaseUrlFromEnv")}</span>
                ) : s.voiceApiBaseEffective ? (
                  <span className="font-mono text-xs text-ink-muted">{t("admin:ifMemActive")}</span>
                ) : null}
              </div>
              <div className="mt-base grid gap-soft sm:grid-cols-2">
                <div>
                  <label className="block text-xs text-ink-muted" htmlFor="voice-stt-provider-id">
                    {t("admin:ifPlatformVoiceSttProvider")}
                  </label>
                  <select
                    id="voice-stt-provider-id"
                    className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                    value={s.voiceSttProviderId || s.voiceSttProviderIdEffective || ""}
                    onChange={(e) => s.setVoiceSttProviderId(e.target.value)}
                    disabled={s.voiceSttProviders.length === 0}
                  >
                    <option value="">{t("admin:ifPlatformVoiceSttProviderAuto")}</option>
                    {s.voiceSttProviders.map((p) => (
                      <option key={`stt-${p.provider_id}`} value={p.provider_id}>
                        {p.label} ({p.provider_id})
                      </option>
                    ))}
                  </select>
                  {s.voiceSttApiBaseEffective ? (
                    <p className="mt-tight font-mono text-meta text-ink-muted">{s.voiceSttApiBaseEffective}</p>
                  ) : null}
                </div>
                <div>
                  <label className="block text-xs text-ink-muted" htmlFor="voice-tts-provider-id">
                    {t("admin:ifPlatformVoiceTtsProvider")}
                  </label>
                  <select
                    id="voice-tts-provider-id"
                    className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                    value={s.voiceTtsProviderId || s.voiceTtsProviderIdEffective || ""}
                    onChange={(e) => s.setVoiceTtsProviderId(e.target.value)}
                    disabled={s.voiceTtsProviders.length === 0}
                  >
                    <option value="">{t("admin:ifPlatformVoiceTtsProviderAuto")}</option>
                    {s.voiceTtsProviders.map((p) => (
                      <option key={`tts-${p.provider_id}`} value={p.provider_id}>
                        {p.label} ({p.provider_id})
                      </option>
                    ))}
                  </select>
                  {s.voiceTtsApiBaseEffective ? (
                    <p className="mt-tight font-mono text-meta text-ink-muted">{s.voiceTtsApiBaseEffective}</p>
                  ) : null}
                </div>
              </div>
              <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformVoiceSttTtsEnvHint")}</p>
              <label className="mt-base block text-xs text-ink-muted" htmlFor="voice-api-base">
                {t("admin:ifPlatformVoiceApiBase")}
              </label>
              <input
                id="voice-api-base"
                className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary disabled:opacity-50"
                value={
                  s.voiceApiBaseSource === "env"
                    ? (s.voiceApiBaseEffective ?? "")
                    : s.voiceApiBaseUrl
                }
                onChange={(e) => s.setVoiceApiBaseUrl(e.target.value)}
                placeholder={t("admin:ifPlatformVoiceApiBasePlaceholder")}
                disabled={s.voiceApiBaseSource === "env"}
              />
              {s.voiceApiBaseSource === "env" ? (
                <p className="mt-tight text-xs text-ink-muted">
                  {voiceEnvPrefixPatterns.map((prefix, index) => (
                    <span key={prefix}>
                      {index > 0 ? " / " : ""}
                      <span className="font-mono">{prefix}</span>
                    </span>
                  ))}{" "}
                  {t("admin:ifMemInDotenv")}{" "}
                  <span className="font-mono">.env</span>
                </p>
              ) : s.voiceApiBaseEffective ? (
                <p className="mt-tight text-xs text-ink-muted">
                  {t("admin:ifMemEffectiveAfterSave")}{" "}
                  <span className="font-mono text-ink-secondary">{s.voiceApiBaseEffective}</span>
                </p>
              ) : null}
              <p className="mt-soft text-xs text-ink-muted">
                {t("admin:ifPlatformVoiceApiKey")}{" "}
                {s.voiceApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
                {s.voiceApiKeySource === "env" ? (
                  <span className="text-badge-warning"> {t("admin:ifMemFromEnv")}</span>
                ) : null}
              </p>
              <label className="mt-base block text-xs text-ink-muted" htmlFor="voice-api-key">
                {t("admin:ifPlatformVoiceApiKey")}
              </label>
              <input
                id="voice-api-key"
                type="password"
                className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary disabled:opacity-50"
                value={s.voiceApiKey}
                onChange={(e) => s.setVoiceApiKey(e.target.value)}
                placeholder={t("admin:ifPlatformVoiceApiKeyPlaceholder")}
                autoComplete="off"
                disabled={s.voiceApiKeySource === "env"}
              />
            </div>
            <div className="mt-wide grid gap-soft sm:grid-cols-2">
              <label className="block text-xs text-ink-muted">
                {t("admin:ifPlatformVoiceSttModel")}
                <ProviderModelSelect
                  id="voice-stt-model"
                  value={s.voiceSttModel}
                  models={sttModels}
                  loading={s.operatorProviderModelsLoading[sttModelsKey]}
                  onChange={(value) => s.setVoiceSttModel(value)}
                  placeholder={t("admin:ifLlmSelectProviderModel")}
                  loadingLabel={t("admin:ifMemLoadingModels")}
                />
              </label>
              <label className="block text-xs text-ink-muted">
                {t("admin:ifPlatformVoiceTtsModel")}
                <ProviderModelSelect
                  id="voice-tts-model"
                  value={s.voiceTtsModel}
                  models={ttsModels}
                  loading={s.operatorProviderModelsLoading[ttsModelsKey]}
                  onChange={(value) => s.setVoiceTtsModel(value)}
                  placeholder={t("admin:ifLlmSelectProviderModel")}
                  loadingLabel={t("admin:ifMemLoadingModels")}
                />
              </label>
            </div>
            <label className="mt-wide block text-xs text-ink-muted">
              {t("admin:ifPlatformVoiceTtsVoice")}
              <input
                className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                value={s.voiceTtsVoice}
                onChange={(e) => s.setVoiceTtsVoice(e.target.value)}
              />
            </label>
            <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.voiceBridgeTelegram}
                onChange={(e) => s.setVoiceBridgeTelegram(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceBridgeTelegram")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.voiceBridgeDiscord}
                onChange={(e) => s.setVoiceBridgeDiscord(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceBridgeDiscord")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.voiceRealtimeEnabled}
                onChange={(e) => s.setVoiceRealtimeEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceRealtime")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.voiceDiscordVcEnabled}
                onChange={(e) => s.setVoiceDiscordVcEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceDiscordVc")}
            </label>
          </section>
          ) : null}

          {showPlatform ? (
          <section className="mt-broad rounded-card border border-line p-wide">
            <h3 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformSurfacesTitle")}</h3>
            <p className="mt-tight text-xs text-ink-muted">{t("admin:ifPlatformSurfacesIntro")}</p>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="surface-preset">
              {t("admin:ifPlatformSurfacePreset")}
            </label>
            <select
              id="surface-preset"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
              value={s.surfacePreset}
              onChange={(e) => {
                const preset = e.target.value as "WEB_ONLY" | "WEB_AND_TUI" | "TUI_ONLY";
                s.setSurfacePreset(preset);
                if (preset === "WEB_ONLY") {
                  s.setWebUiEnabled(true);
                  s.setApiKeyClientsEnabled(false);
                } else if (preset === "TUI_ONLY") {
                  s.setWebUiEnabled(false);
                  s.setApiKeyClientsEnabled(true);
                } else {
                  s.setWebUiEnabled(true);
                  s.setApiKeyClientsEnabled(true);
                }
              }}
            >
              <option value="WEB_AND_TUI">{t("admin:ifPlatformSurfaceWebAndTui")}</option>
              <option value="WEB_ONLY">{t("admin:ifPlatformSurfaceWebOnly")}</option>
              <option value="TUI_ONLY">{t("admin:ifPlatformSurfaceTuiOnly")}</option>
            </select>
            <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.webUiEnabled}
                onChange={(e) => {
                  const on = e.target.checked;
                  s.setWebUiEnabled(on);
                  if (on && s.apiKeyClientsEnabled) s.setSurfacePreset("WEB_AND_TUI");
                  else if (on) s.setSurfacePreset("WEB_ONLY");
                  else s.setSurfacePreset("TUI_ONLY");
                }}
              />
              {t("admin:ifPlatformWebUiEnabled")}
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.apiKeyClientsEnabled}
                onChange={(e) => {
                  const on = e.target.checked;
                  s.setApiKeyClientsEnabled(on);
                  if (s.webUiEnabled && on) s.setSurfacePreset("WEB_AND_TUI");
                  else if (s.webUiEnabled) s.setSurfacePreset("WEB_ONLY");
                  else s.setSurfacePreset("TUI_ONLY");
                }}
              />
              {t("admin:ifPlatformApiKeyClientsEnabled")}
            </label>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="api-key-ws-modes">
              {t("admin:ifPlatformApiKeyWorkspaceModes")}
            </label>
            <select
              id="api-key-ws-modes"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
              value={s.apiKeyWorkspaceModes}
              onChange={(e) =>
                s.setApiKeyWorkspaceModes(e.target.value as "server" | "client" | "both")
              }
              disabled={!s.apiKeyClientsEnabled}
            >
              <option value="both">{t("admin:ifPlatformApiKeyModesBoth")}</option>
              <option value="server">{t("admin:ifPlatformApiKeyModesServer")}</option>
              <option value="client">{t("admin:ifPlatformApiKeyModesClient")}</option>
            </select>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformApiKeyModesHint")}</p>
            <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.serverWorkspacesAdminOnly}
                onChange={(e) => s.setServerWorkspacesAdminOnly(e.target.checked)}
              />
              {t("admin:ifPlatformServerWorkspacesAdminOnly")}
            </label>
            <p className="mt-base text-xs text-ink-muted">
              {t("admin:ifPlatformServerWorkspacesAdminOnlyHint")}
            </p>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="ws-index-consent-max">
              {t("admin:ifPlatformIndexConsentMax")}
            </label>
            <select
              id="ws-index-consent-max"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
              value={s.workspaceIndexConsentMax}
              onChange={(e) => s.setWorkspaceIndexConsentMax(e.target.value)}
            >
              <option value="text">{t("admin:ifPlatformIndexConsentText")}</option>
              <option value="symbols">{t("admin:ifPlatformIndexConsentSymbols")}</option>
              <option value="none">{t("admin:ifPlatformIndexConsentNone")}</option>
            </select>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformIndexConsentHint")}</p>
          </section>
          ) : null}

          {showPlatform ? (
          <section className="mt-broad rounded-card border border-line p-wide">
            <h3 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformWorkspacesTitle")}</h3>
            <p className="mt-tight text-xs text-ink-muted">{t("admin:ifPlatformWorkspacesIntro")}</p>
            <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.workspaceAllowSelfEditing}
                onChange={(e) => s.setWorkspaceAllowSelfEditing(e.target.checked)}
              />
              {t("admin:ifPlatformSelfWorkspace")}
            </label>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformSelfWorkspaceHint")}</p>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="ws-index-on-write-default">
              Default index-on-write (new workspaces inherit via null override)
            </label>
            <select
              id="ws-index-on-write-default"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
              value={s.workspaceIndexOnWriteDefault}
              onChange={(e) => s.setWorkspaceIndexOnWriteDefault(e.target.value)}
            >
              <option value="debounced">debounced (recommended)</option>
              <option value="immediate">immediate</option>
              <option value="off">off</option>
            </select>
            <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.workspaceReindexAfterGitPull}
                onChange={(e) => s.setWorkspaceReindexAfterGitPull(e.target.checked)}
              />
              Reindex code after successful git pull
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.workspaceNightlyReindexEnabled}
                onChange={(e) => s.setWorkspaceNightlyReindexEnabled(e.target.checked)}
              />
              Nightly reindex for stale workspaces (hourly check, max 100)
            </label>
            <label className="mt-base flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.workspaceIndexOnAttachEnabled}
                onChange={(e) => s.setWorkspaceIndexOnAttachEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformIndexOnAttach")}
            </label>
          </section>
          ) : null}
    </>
  );
}
