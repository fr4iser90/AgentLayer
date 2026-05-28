import { AdminInterfacesMemorySection } from "./AdminInterfacesMemorySection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesMemoryPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:memoryRagTitle")}
      description={t("admin:interfacesMemoryDescription")}
      wide
    >
      <AdminInterfacesMemorySection />
    </AdminInterfacesPageShell>
  );
}
