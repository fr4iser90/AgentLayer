import { useTranslation } from "react-i18next";
import { OrgContentCms } from "./OrgContentCms";
import { PageShell } from "../../layout/PageShell";

export function OrgKnowledgePage() {
  const { t } = useTranslation(["org"]);
  return (
    <PageShell density="wide">
      <h1 className="text-xl font-semibold text-ink-primary">{t("org:knowledgePageTitle")}</h1>
      <p className="mt-base text-sm text-ink-muted">{t("org:knowledgePageIntro")}</p>
      <div className="mt-deep">
        <OrgContentCms />
      </div>
    </PageShell>
  );
}
