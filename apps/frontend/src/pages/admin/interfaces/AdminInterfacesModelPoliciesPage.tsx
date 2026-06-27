import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesModelPoliciesPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesModelPoliciesTitle")}
      description={t("admin:interfacesModelPoliciesDescription")}
      wide
    >
      <AdminInterfacesLlmSection mode="policies" />
    </AdminInterfacesPageShell>
  );
}
