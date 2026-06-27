import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesProvidersPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesProvidersTitle")}
      description={t("admin:interfacesProvidersDescription")}
      wide
    >
      <AdminInterfacesLlmSection mode="providers" />
    </AdminInterfacesPageShell>
  );
}
