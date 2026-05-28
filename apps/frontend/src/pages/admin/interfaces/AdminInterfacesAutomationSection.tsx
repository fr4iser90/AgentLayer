import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useTranslation } from "react-i18next";

export function AdminInterfacesAutomationSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
      <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:ifAutoSchedulerTitle")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifAutoSchedulerIntro")}</p>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.schedulerEnabled}
            onChange={(e) => s.setSchedulerEnabled(e.target.checked)}
          />
          {t("admin:ifAutoSchedulerEnable")}
        </label>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-interval">
          {t("admin:ifAutoInterval")}
        </label>
        <input
          id="hb-interval"
          type="number"
          min={5}
          max={1440}
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerIntervalMin}
          onChange={(e) => s.setSchedulerIntervalMin(e.target.value)}
        />
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-user">
          {t("admin:ifAutoUser")}
        </label>
        <select
          id="hb-user"
          className="mt-1 w-full max-w-xl rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerUserId}
          onChange={(e) => s.setSchedulerUserId(e.target.value)}
        >
          <option value="">{t("admin:ifAutoSelectUser")}</option>
          {s.adminUsers.map((u) => (
            <option key={u.id} value={u.id}>
              {(u.email || u.display_name || u.id).trim() || u.id}
            </option>
          ))}
        </select>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-model">
          {t("admin:ifAutoModel")}
        </label>
        <input
          id="hb-model"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerModel}
          onChange={(e) => s.setSchedulerModel(e.target.value)}
          placeholder={t("admin:ifAutomationModelPlaceholder")}
        />
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-rounds">
          {t("admin:ifAutoMaxRounds")}
        </label>
        <input
          id="hb-rounds"
          type="number"
          min={1}
          max={64}
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerMaxRounds}
          onChange={(e) => s.setSchedulerMaxRounds(e.target.value)}
          placeholder={t("admin:ifAutomationConcurrencyPlaceholder")}
        />
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.schedulerNotifyOnlyIfNotOk}
            onChange={(e) => s.setSchedulerNotifyOnlyIfNotOk(e.target.checked)}
          />
          {t("admin:ifAutoNotifyOnly")}
        </label>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-out">
          {t("admin:ifAutoMaxOutbound")}
        </label>
        <input
          id="hb-out"
          type="number"
          min={0}
          max={100000}
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerMaxOutbound}
          onChange={(e) => s.setSchedulerMaxOutbound(e.target.value)}
        />
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-pkg">
          {t("admin:ifAutoPackages")}
        </label>
        <input
          id="hb-pkg"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerPackages}
          onChange={(e) => s.setSchedulerPackages(e.target.value)}
          placeholder={t("admin:ifAutomationPluginsPlaceholder")}
        />
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-llm">
          {t("admin:ifAutoLlmBackend")}
        </label>
        <select
          id="hb-llm"
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerLlmBackend}
          onChange={(e) => s.setSchedulerLlmBackend(e.target.value)}
        >
          <option value="inherit">{t("admin:ifAutoLlmInherit")}</option>
          <option value="ollama">ollama</option>
          <option value="external">external</option>
        </select>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-tools">
          {t("admin:ifAutoToolsMode")}
        </label>
        <select
          id="hb-tools"
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerToolsMode}
          onChange={(e) => s.setSchedulerToolsMode(e.target.value)}
        >
          <option value="none">{t("admin:ifAutoToolsNone")}</option>
          <option value="allowlist">{t("admin:ifAutoToolsAllowlist")}</option>
          <option value="full">{t("admin:ifAutoToolsFull")}</option>
        </select>
        <p className="mt-4 rounded-md border border-white/10 bg-black/20 px-3 py-2 text-xs text-surface-muted">
          {t("admin:ifAutoLegacyNote")}
        </p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-instr">
          {t("admin:ifAutoInstructions")}
        </label>
        <textarea
          id="hb-instr"
          rows={4}
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.schedulerInstructions}
          onChange={(e) => s.setSchedulerInstructions(e.target.value)}
          placeholder={t("admin:ifAutomationHeartbeatPlaceholder")}
        />
        <p className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">
          {t("admin:ifAutoPersistedJobs")}
        </p>
        <p className="mt-1 text-xs text-surface-muted">
          {t("admin:ifAutoPersistedJobsIntro")} {t("admin:ifAutomationDbHint")}
        </p>
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.schedulerJobsWorkerEnabled}
            onChange={(e) => s.setSchedulerJobsWorkerEnabled(e.target.checked)}
          />
          {t("admin:ifAutoWorkerEnable")}
        </label>
      </section>
    </>
  );
}
