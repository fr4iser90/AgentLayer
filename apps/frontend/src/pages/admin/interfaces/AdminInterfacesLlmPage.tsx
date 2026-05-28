import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesLlmPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:llmRouting")}
      description={t("admin:interfacesLlmDescription")}
      wide
    >
      <AdminInterfacesLlmSection />
    </AdminInterfacesPageShell>
  );
}
