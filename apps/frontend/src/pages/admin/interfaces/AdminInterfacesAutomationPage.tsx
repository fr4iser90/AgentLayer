import { Link } from "react-router-dom";
import { AdminInterfacesAutomationSection } from "./AdminInterfacesAutomationSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesAutomationPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:navAutomation")}
      description={
        <>
          {t("admin:interfacesAutomationDescriptionPrefix")}{" "}
          <span className="font-mono text-neutral-300">scheduler_jobs</span>{" "}
          {t("admin:interfacesAutomationDescriptionWorker")}{" "}
          <Link to="/admin/schedules" className="text-sky-400 hover:underline">
            {t("admin:schedulesTitle")}
          </Link>
          {t("admin:interfacesAutomationDescriptionSuffix")}
        </>
      }
    >
      <AdminInterfacesAutomationSection />
    </AdminInterfacesPageShell>
  );
}
