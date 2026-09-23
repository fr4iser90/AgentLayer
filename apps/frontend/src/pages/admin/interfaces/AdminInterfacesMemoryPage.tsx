import { AdminInterfacesMemorySection } from "./AdminInterfacesMemorySection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../auth/AuthContext";
import { hasOrgSurface } from "../../../auth/deploymentMode";
import { OrgContentCms } from "../../org/OrgContentCms";

export function AdminInterfacesMemoryPage() {
  const { t } = useTranslation(["admin", "org"]);
  const { user } = useAuth();
  const showContentCms = !hasOrgSurface(user);

  return (
    <AdminInterfacesPageShell
      title={t("admin:memoryRagTitle")}
      description={t("admin:interfacesMemoryDescription")}
      wide
    >
      <AdminInterfacesMemorySection />
      {showContentCms ? (
        <div className="mt-8">
          <h2 className="mb-4 text-sm font-medium text-ink-primary">{t("org:knowledgePageTitle")}</h2>
          <OrgContentCms />
        </div>
      ) : null}
    </AdminInterfacesPageShell>
  );
}
