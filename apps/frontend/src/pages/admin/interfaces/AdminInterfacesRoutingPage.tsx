import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesRoutingPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesRoutingTitle")}
      description={t("admin:interfacesRoutingDescription")}
      wide
    >
      <AdminInterfacesLlmSection mode="routing" />
    </AdminInterfacesPageShell>
  );
}
