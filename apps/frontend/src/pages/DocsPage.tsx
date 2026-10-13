import { useTranslation } from "react-i18next";

const REPO =
  "https://github.com/fr4iser90/AgentLayer_-_Jetson-Orin-Nano-Super-Developer-Kit-dedicated";

export function DocsPage() {
  const { t } = useTranslation(["common"]);
  const LINKS: { labelKey: "docs.repository" | "docs.docsFolder" | "docs.webuiContract" | "docs.frontendPlan"; href: string }[] = [
    { labelKey: "docs.repository", href: REPO },
    { labelKey: "docs.docsFolder", href: `${REPO}/tree/main/docs` },
    { labelKey: "docs.webuiContract", href: `${REPO}/blob/main/docs/WEBUI_CONTRACT.md` },
    { labelKey: "docs.frontendPlan", href: `${REPO}/blob/main/docs/FRONTEND_AGENT_UI_PLAN.md` },
  ];

  return (
    <div className="h-full min-h-0 overflow-y-auto px-broad py-deep">
      <div className="mx-auto max-w-measure">
        <h1 className="text-lg font-semibold text-ink-primary">{t("common:docs.title")}</h1>
        <p className="mt-base text-sm text-ink-muted">
          {t("common:docs.intro")}{" "}
          <code className="rounded-tile bg-white/5 px-tight py-hair text-xs text-ink-secondary">docs/</code>.
        </p>
        <ul className="mt-broad flex flex-col gap-base">
          {LINKS.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-accent hover:text-badge-accent hover:underline"
              >
                {t(`common:${item.labelKey}`)}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
