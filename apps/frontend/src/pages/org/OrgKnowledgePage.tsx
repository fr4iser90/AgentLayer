import { useTranslation } from "react-i18next";
import { OrgKnowledgePublishSection } from "./OrgKnowledgePublishSection";

export function OrgKnowledgePage() {
  const { t } = useTranslation(["org"]);
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">{t("org:knowledgePageTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("org:knowledgePageIntro")}</p>
      <p className="mt-2 text-xs text-amber-300/90">{t("org:knowledgePilotNote")}</p>
      <div className="mt-8">
        <OrgKnowledgePublishSection />
      </div>
    </div>
  );
}
