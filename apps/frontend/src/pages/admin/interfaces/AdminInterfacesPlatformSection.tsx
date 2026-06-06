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
          </section>          <section className="mt-6 rounded-lg border border-surface-border p-4">
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
