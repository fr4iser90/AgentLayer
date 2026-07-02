import { useTranslation } from "react-i18next";
import { OrgContentCms } from "./OrgContentCms";

export function OrgKnowledgePage() {
  const { t } = useTranslation(["org"]);
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">{t("org:knowledgePageTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("org:knowledgePageIntro")}</p>
      <div className="mt-8">
        <OrgContentCms />
      </div>
    </div>
  );
}
