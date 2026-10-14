import { AdminInterfacesPlatformSection } from "./AdminInterfacesPlatformSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesPlatformPage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesPlatformTitle")}
      description={t("admin:interfacesPlatformDescription")}
      wide
    >
      <AdminInterfacesPlatformSection mode="platform" />
    </AdminInterfacesPageShell>
  );
}
