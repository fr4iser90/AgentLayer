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
    <div className="h-full min-h-0 overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-xl">
        <h1 className="text-lg font-semibold text-white">{t("common:docs.title")}</h1>
        <p className="mt-2 text-sm text-surface-muted">
          {t("common:docs.intro")}{" "}
          <code className="rounded bg-white/5 px-1 py-0.5 text-xs text-neutral-300">docs/</code>.
        </p>
        <ul className="mt-6 flex flex-col gap-2">
          {LINKS.map((item) => (
            <li key={item.href}>
              <a
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-sky-400 hover:text-sky-300 hover:underline"
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
