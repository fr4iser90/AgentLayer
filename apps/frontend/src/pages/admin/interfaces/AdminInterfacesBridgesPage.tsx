import { AdminInterfacesBridgesSection } from "./AdminInterfacesBridgesSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesBridgesPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:bridges")}
      description={t("admin:interfacesBridgesDescription")}
    >
      <AdminInterfacesBridgesSection />
    </AdminInterfacesPageShell>
  );
}
