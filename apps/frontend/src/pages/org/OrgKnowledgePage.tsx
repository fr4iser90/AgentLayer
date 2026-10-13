import { useTranslation } from "react-i18next";
import { OrgContentCms } from "./OrgContentCms";

export function OrgKnowledgePage() {
  const { t } = useTranslation(["org"]);
  return (
    <div className="mx-auto max-w-pageWide px-broad py-page">
      <h1 className="text-xl font-semibold text-ink-primary">{t("org:knowledgePageTitle")}</h1>
      <p className="mt-base text-sm text-ink-muted">{t("org:knowledgePageIntro")}</p>
      <div className="mt-deep">
        <OrgContentCms />
      </div>
    </div>
  );
}
