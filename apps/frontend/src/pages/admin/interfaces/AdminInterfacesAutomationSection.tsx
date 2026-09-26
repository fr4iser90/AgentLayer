import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useTranslation } from "react-i18next";
import { Select, TextArea, TextInput } from "../../../ui/Field";

export function AdminInterfacesAutomationSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-ink-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
      <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifAutoSchedulerTitle")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifAutoSchedulerIntro")}</p>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.schedulerEnabled}
            onChange={(e) => s.setSchedulerEnabled(e.target.checked)}
          />
          {t("admin:ifAutoSchedulerEnable")}
        </label>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-interval">
          {t("admin:ifAutoInterval")}
        </label>
        <TextInput
          mono
          id="hb-interval"
          type="number"
          min={5}
          max={1440}
          className="mt-tight max-w-control"
          value={s.schedulerIntervalMin}
          onChange={(e) => s.setSchedulerIntervalMin(e.target.value)}
        />
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-user">
          {t("admin:ifAutoUser")}
        </label>
        <Select
          id="hb-user"
          className="mt-tight max-w-controlWide"
          value={s.schedulerUserId}
          onChange={(e) => s.setSchedulerUserId(e.target.value)}
        >
          <option value="">{t("admin:ifAutoSelectUser")}</option>
          {s.adminUsers.map((u) => (
            <option key={u.id} value={u.id}>
              {(u.email || u.display_name || u.id).trim() || u.id}
            </option>
          ))}
        </Select>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-model">
          {t("admin:ifAutoModel")}
        </label>
        <TextInput
          mono
          id="hb-model"
          className="mt-tight max-w-controlWide"
          value={s.schedulerModel}
          onChange={(e) => s.setSchedulerModel(e.target.value)}
          placeholder={t("admin:ifAutomationModelPlaceholder")}
        />
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-rounds">
          {t("admin:ifAutoMaxRounds")}
        </label>
        <TextInput
          mono
          id="hb-rounds"
          type="number"
          min={1}
          max={64}
          className="mt-tight max-w-control"
          value={s.schedulerMaxRounds}
          onChange={(e) => s.setSchedulerMaxRounds(e.target.value)}
          placeholder={t("admin:ifAutomationConcurrencyPlaceholder")}
        />
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.schedulerNotifyOnlyIfNotOk}
            onChange={(e) => s.setSchedulerNotifyOnlyIfNotOk(e.target.checked)}
          />
          {t("admin:ifAutoNotifyOnly")}
        </label>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-out">
          {t("admin:ifAutoMaxOutbound")}
        </label>
        <TextInput
          mono
          id="hb-out"
          type="number"
          min={0}
          max={100000}
          className="mt-tight max-w-control"
          value={s.schedulerMaxOutbound}
          onChange={(e) => s.setSchedulerMaxOutbound(e.target.value)}
        />
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-pkg">
          {t("admin:ifAutoPackages")}
        </label>
        <TextInput
          mono
          id="hb-pkg"
          className="mt-tight"
          value={s.schedulerPackages}
          onChange={(e) => s.setSchedulerPackages(e.target.value)}
          placeholder={t("admin:ifAutomationPluginsPlaceholder")}
        />
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-llm">
          {t("admin:ifAutoLlmBackend")}
        </label>
        <Select
          id="hb-llm"
          className="mt-tight max-w-control"
          value={s.schedulerLlmBackend}
          onChange={(e) => s.setSchedulerLlmBackend(e.target.value)}
        >
          <option value="inherit">{t("admin:ifAutoLlmInherit")}</option>
          <option value="provider">{t("admin:ifAutoLlmProvider")}</option>
          <option value="provider_db">{t("admin:ifAutoLlmProviderDb")}</option>
        </Select>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-tools">
          {t("admin:ifAutoToolsMode")}
        </label>
        <Select
          id="hb-tools"
          className="mt-tight max-w-control"
          value={s.schedulerToolsMode}
          onChange={(e) => s.setSchedulerToolsMode(e.target.value)}
        >
          <option value="none">{t("admin:ifAutoToolsNone")}</option>
          <option value="allowlist">{t("admin:ifAutoToolsAllowlist")}</option>
          <option value="full">{t("admin:ifAutoToolsFull")}</option>
        </Select>
        <p className="mt-wide rounded-tile border border-line bg-black/20 px-soft py-base text-xs text-ink-muted">
          {t("admin:ifAutoLegacyNote")}
        </p>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="hb-instr">
          {t("admin:ifAutoInstructions")}
        </label>
        <TextArea
          mono
          id="hb-instr"
          rows={4}
          className="mt-tight"
          value={s.schedulerInstructions}
          onChange={(e) => s.setSchedulerInstructions(e.target.value)}
          placeholder={t("admin:ifAutomationHeartbeatPlaceholder")}
        />
        <p className="mt-broad text-xs font-medium uppercase tracking-wide text-ink-muted">
          {t("admin:ifAutoPersistedJobs")}
        </p>
        <p className="mt-tight text-xs text-ink-muted">
          {t("admin:ifAutoPersistedJobsIntro")} {t("admin:ifAutomationDbHint")}
        </p>
        <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.schedulerJobsWorkerEnabled}
            onChange={(e) => s.setSchedulerJobsWorkerEnabled(e.target.checked)}
          />
          {t("admin:ifAutoWorkerEnable")}
        </label>
      </section>
    </>
  );
}
