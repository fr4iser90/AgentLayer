import { Link } from "react-router-dom";
import { AdminInterfacesAutomationSection } from "./AdminInterfacesAutomationSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesAutomationPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesAutomationTitle")}
      description={
        <>
          {t("admin:interfacesAutomationDescriptionPrefix")}{" "}
          <span className="font-mono text-ink-secondary">scheduler_jobs</span>{" "}
          {t("admin:interfacesAutomationDescriptionWorker")}{" "}
          <Link to="/admin/schedules" className="text-accent hover:underline">
            {t("admin:schedulesTitle")}
          </Link>
          {t("admin:interfacesAutomationDescriptionSuffix")}
        </>
      }
    >
      <AdminInterfacesAutomationSection />
      <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:pluginCronTitle")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:pluginCronIntro")}</p>
        <p className="mt-wide text-xs text-ink-muted">{t("admin:pluginCronLlmNote")}</p>
        <p className="mt-wide text-xs text-ink-muted">{t("admin:pluginCronNoApi")}</p>
      </section>
    </AdminInterfacesPageShell>
  );
}
