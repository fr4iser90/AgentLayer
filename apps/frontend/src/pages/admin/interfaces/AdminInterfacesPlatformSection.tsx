import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useTranslation } from "react-i18next";

export function AdminInterfacesPlatformSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">{t("admin:ifPlatformAgentModeTitle")}</h2>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformAgentModeIntro")}</p>
            <p className="mt-2 text-xs text-surface-muted">
              {t("admin:ifPlatformAgentModeEnvEffective", {
                env: s.agentModeEnv,
                effective: s.agentModeEffective,
              })}
            </p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="agent-mode">
              {t("admin:ifPlatformAgentModeOverride")}
            </label>
            <select
              id="agent-mode"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={s.agentMode}
              onChange={(e) => s.setAgentMode(e.target.value as "env" | "sandbox" | "host")}
            >
              <option value="env">{t("admin:ifPlatformAgentModeUseEnv")}</option>
              <option value="sandbox">{t("admin:ifPlatformAgentModeSandbox")}</option>
              <option value="host">{t("admin:ifPlatformAgentModeHost")}</option>
            </select>
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">{t("admin:ifPlatformDashboardUploadsTitle")}</h2>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformUploadIntro")}</p>
            {s.uploadEffBytes != null ? (
              <p className="mt-2 text-xs text-surface-muted">
                {t("admin:ifPlatformUploadEffective", {
                  bytes: s.uploadEffBytes,
                  mime: s.uploadEffMime.join(", ") || "—",
                })}
              </p>
            ) : null}
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mb">
              {t("admin:ifPlatformUploadMaxMb")}
            </label>
            <input
              id="wu-mb"
              type="number"
              min={1}
              max={512}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.uploadMaxMb}
              onChange={(e) => s.setUploadMaxMb(e.target.value)}
              placeholder={t("admin:ifPlatformUploadMbPlaceholder")}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mime">
              {t("admin:ifPlatformUploadMime")}
            </label>
            <input
              id="wu-mime"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.uploadMime}
              onChange={(e) => s.setUploadMime(e.target.value)}
              placeholder={t("admin:ifPlatformMimePlaceholder")}
            />
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">{t("admin:ifPlatformMediaTitle")}</h2>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformMediaIntro")}</p>
            {s.mediaEffUploadBytes != null ? (
              <p className="mt-2 text-xs text-surface-muted">
                {t("admin:ifPlatformMediaEffective", {
                  bytes: s.mediaEffUploadBytes,
                  mime: s.mediaEffUploadMime.join(", ") || "—",
                  quotaMb: s.mediaEffDefaultQuotaMb ?? "—",
                })}
              </p>
            ) : null}
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.mediaLibraryEnabled}
                onChange={(e) => s.setMediaLibraryEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaLibraryEnabled")}
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.mediaUserUploadEnabled}
                onChange={(e) => s.setMediaUserUploadEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaUploadEnabled")}
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.mediaSharingEnabled}
                onChange={(e) => s.setMediaSharingEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformMediaSharingEnabled")}
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="media-quota-mb">
              {t("admin:ifPlatformMediaDefaultQuotaMb")}
            </label>
            <input
              id="media-quota-mb"
              type="number"
              min={1}
              max={50000}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.mediaDefaultQuotaMb}
              onChange={(e) => s.setMediaDefaultQuotaMb(e.target.value)}
              placeholder={t("admin:ifPlatformMediaQuotaPlaceholder")}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="media-upload-mb">
              {t("admin:ifPlatformMediaUploadMaxMb")}
            </label>
            <input
              id="media-upload-mb"
              type="number"
              min={1}
              max={512}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.mediaUploadMaxMb}
              onChange={(e) => s.setMediaUploadMaxMb(e.target.value)}
              placeholder={t("admin:ifPlatformUploadMbPlaceholder")}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="media-mime">
              {t("admin:ifPlatformMediaUploadMime")}
            </label>
            <input
              id="media-mime"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.mediaUploadMime}
              onChange={(e) => s.setMediaUploadMime(e.target.value)}
              placeholder={t("admin:ifPlatformMimePlaceholder")}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="media-embed-hosts">
              {t("admin:ifPlatformMediaEmbedHosts")}
            </label>
            <input
              id="media-embed-hosts"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.mediaEmbedHosts}
              onChange={(e) => s.setMediaEmbedHosts(e.target.value)}
              placeholder={t("admin:ifPlatformMediaEmbedHostsPlaceholder")}
            />
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">{t("admin:ifPlatformVoiceTitle")}</h2>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformVoiceIntro")}</p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.voiceEnabled}
                onChange={(e) => s.setVoiceEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceEnabled")}
            </label>
            <div className="mt-4 rounded-lg border border-white/10 bg-black/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-surface-muted">{t("admin:ifPlatformVoiceEndpoint")}</span>
                {s.voiceApiBaseSource === "env" ? (
                  <span className="text-xs text-amber-300/90">{t("admin:ifPlatformVoiceBaseUrlFromEnv")}</span>
                ) : s.voiceApiBaseEffective ? (
                  <span className="font-mono text-xs text-neutral-500">{t("admin:ifMemActive")}</span>
                ) : null}
              </div>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="block text-xs text-surface-muted" htmlFor="voice-stt-provider-id">
                    {t("admin:ifPlatformVoiceSttProvider")}
                  </label>
                  <select
                    id="voice-stt-provider-id"
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
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
                    <p className="mt-1 font-mono text-[10px] text-neutral-400">{s.voiceSttApiBaseEffective}</p>
                  ) : null}
                </div>
                <div>
                  <label className="block text-xs text-surface-muted" htmlFor="voice-tts-provider-id">
                    {t("admin:ifPlatformVoiceTtsProvider")}
                  </label>
                  <select
                    id="voice-tts-provider-id"
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
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
                    <p className="mt-1 font-mono text-[10px] text-neutral-400">{s.voiceTtsApiBaseEffective}</p>
                  ) : null}
                </div>
              </div>
              <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformVoiceSttTtsEnvHint")}</p>
              <label className="mt-2 block text-xs text-surface-muted" htmlFor="voice-api-base">
                {t("admin:ifPlatformVoiceApiBase")}
              </label>
              <input
                id="voice-api-base"
                className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
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
                <p className="mt-1 text-xs text-surface-muted">
                  <span className="font-mono">VOICE_STT_PROVIDER_N_*</span> /{" "}
                  <span className="font-mono">VOICE_TTS_PROVIDER_N_*</span> {t("admin:ifMemInDotenv")}{" "}
                  <span className="font-mono">.env</span>
                </p>
              ) : s.voiceApiBaseEffective ? (
                <p className="mt-1 text-xs text-surface-muted">
                  {t("admin:ifMemEffectiveAfterSave")}{" "}
                  <span className="font-mono text-neutral-300">{s.voiceApiBaseEffective}</span>
                </p>
              ) : null}
              <p className="mt-3 text-xs text-surface-muted">
                {t("admin:ifPlatformVoiceApiKey")}{" "}
                {s.voiceApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
                {s.voiceApiKeySource === "env" ? (
                  <span className="text-amber-300/90"> {t("admin:ifMemFromEnv")}</span>
                ) : null}
              </p>
              <label className="mt-2 block text-xs text-surface-muted" htmlFor="voice-api-key">
                {t("admin:ifPlatformVoiceApiKey")}
              </label>
              <input
                id="voice-api-key"
                type="password"
                className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
                value={s.voiceApiKey}
                onChange={(e) => s.setVoiceApiKey(e.target.value)}
                placeholder={t("admin:ifPlatformVoiceApiKeyPlaceholder")}
                autoComplete="off"
                disabled={s.voiceApiKeySource === "env"}
              />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block text-xs text-surface-muted">
                {t("admin:ifPlatformVoiceSttModel")}
                <input
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.voiceSttModel}
                  onChange={(e) => s.setVoiceSttModel(e.target.value)}
                />
              </label>
              <label className="block text-xs text-surface-muted">
                {t("admin:ifPlatformVoiceTtsModel")}
                <input
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.voiceTtsModel}
                  onChange={(e) => s.setVoiceTtsModel(e.target.value)}
                />
              </label>
            </div>
            <label className="mt-4 block text-xs text-surface-muted">
              {t("admin:ifPlatformVoiceTtsVoice")}
              <input
                className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                value={s.voiceTtsVoice}
                onChange={(e) => s.setVoiceTtsVoice(e.target.value)}
              />
            </label>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.voiceBridgeTelegram}
                onChange={(e) => s.setVoiceBridgeTelegram(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceBridgeTelegram")}
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.voiceBridgeDiscord}
                onChange={(e) => s.setVoiceBridgeDiscord(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceBridgeDiscord")}
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.voiceRealtimeEnabled}
                onChange={(e) => s.setVoiceRealtimeEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceRealtime")}
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.voiceDiscordVcEnabled}
                onChange={(e) => s.setVoiceDiscordVcEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformVoiceDiscordVc")}
            </label>
          </section>

          <section className="mt-6 rounded-lg border border-surface-border p-4">
            <h3 className="text-sm font-medium text-white">{t("admin:ifPlatformWorkspacesTitle")}</h3>
            <p className="mt-1 text-xs text-surface-muted">{t("admin:ifPlatformWorkspacesIntro")}</p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.workspaceAllowSelfEditing}
                onChange={(e) => s.setWorkspaceAllowSelfEditing(e.target.checked)}
              />
              {t("admin:ifPlatformSelfWorkspace")}
            </label>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformSelfWorkspaceHint")}</p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="ws-index-on-write-default">
              Default index-on-write (new workspaces inherit via null override)
            </label>
            <select
              id="ws-index-on-write-default"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={s.workspaceIndexOnWriteDefault}
              onChange={(e) => s.setWorkspaceIndexOnWriteDefault(e.target.value)}
            >
              <option value="debounced">debounced (recommended)</option>
              <option value="immediate">immediate</option>
              <option value="off">off</option>
            </select>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.workspaceReindexAfterGitPull}
                onChange={(e) => s.setWorkspaceReindexAfterGitPull(e.target.checked)}
              />
              Reindex code after successful git pull
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.workspaceNightlyReindexEnabled}
                onChange={(e) => s.setWorkspaceNightlyReindexEnabled(e.target.checked)}
              />
              Nightly reindex for stale workspaces (hourly check, max 100)
            </label>
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.workspaceIndexOnAttachEnabled}
                onChange={(e) => s.setWorkspaceIndexOnAttachEnabled(e.target.checked)}
              />
              {t("admin:ifPlatformIndexOnAttach")}
            </label>
          </section>
    </>
  );
}
