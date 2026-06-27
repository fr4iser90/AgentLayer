import { AdminInterfacesPlatformSection } from "./AdminInterfacesPlatformSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";

export function AdminInterfacesVoicePage() {
  const { t } = useTranslation(["admin"]);
  return (
    <AdminInterfacesPageShell
      title={t("admin:interfacesVoiceTitle")}
      description={t("admin:interfacesVoiceDescription")}
      wide
    >
      <AdminInterfacesPlatformSection mode="voice" />
    </AdminInterfacesPageShell>
  );
}
