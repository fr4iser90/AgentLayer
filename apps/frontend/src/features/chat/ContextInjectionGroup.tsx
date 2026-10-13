import { memo } from "react";
import { useTranslation } from "react-i18next";
import { ContextInjectionBadge } from "./ContextInjectionBadge";
import {
  approxTokensFromChars,
  injectItemCharCount,
} from "./contextInjectBudget";

export type ContextInjectItem = {
  key: string;
  label: string;
  body?: string;
  chars?: number;
  injectKind?: string;
};

/** One collapsed summary for all turn context injections (expand → per-block badges). */
export const ContextInjectionGroup = memo(function ContextInjectionGroup({
  items,
}: {
  items: ContextInjectItem[];
}) {
  const { t } = useTranslation(["chat"]);
  if (!items.length) return null;

  const totalChars = items.reduce((sum, it) => sum + injectItemCharCount(it), 0);
  const totalTokens = approxTokensFromChars(totalChars);

  const priority = (kind?: string) => {
    const k = (kind || "").toLowerCase();
    if (k === "agents_md") return 0;
    if (k === "agent_system_prompt") return 1;
    if (k === "workspace_bound" || k === "workspace_retrieval") return 2;
    if (k === "skills") return 3;
    if (k === "context_omit_stub") return 20;
    return 10;
  };
  const sorted = [...items].sort(
    (a, b) => priority(a.injectKind) - priority(b.injectKind)
  );
  const highlight = sorted
    .slice(0, 3)
    .map((it) => it.label)
    .filter(Boolean);
  const more = Math.max(0, items.length - highlight.length);

  return (
    <details className="mb-soft group">
      <summary className="inline-flex max-w-full cursor-pointer list-none flex-wrap items-center gap-snug rounded-tile border border-warning/35 bg-warning-subtle px-firm py-snug text-meta font-medium text-badge-warning marker:content-none [&::-webkit-details-marker]:hidden hover:bg-warning-subtle">
        <span className="relative flex h-1.5 w-1.5 shrink-0" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-pill bg-warning opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-pill bg-warning" />
        </span>
        <span>{t("chat:contextInjectGroupTitle", { count: items.length })}</span>
        {totalChars > 0 ? (
          <span
            className="text-meta font-normal text-badge-warning"
            title={t("chat:contextInjectTokensHint")}
          >
            {t("chat:contextInjectBudget", {
              chars: totalChars,
              tokens: totalTokens,
            })}
          </span>
        ) : null}
        {highlight.length > 0 ? (
          <span className="max-w-chipWide truncate text-meta font-normal text-badge-warning">
            {highlight.join(" · ")}
            {more > 0 ? ` · +${more}` : ""}
          </span>
        ) : null}
        <span className="text-meta font-normal text-badge-warning group-open:hidden">
          {t("chat:contextInjectExpandHint")}
        </span>
        <span className="hidden text-meta font-normal text-badge-warning group-open:inline">
          {t("chat:contextInjectCollapseHint")}
        </span>
      </summary>
      <div className="mt-base flex flex-col gap-tight border-l border-warning/20 pl-base">
        {sorted.map((it) => (
          <ContextInjectionBadge
            key={it.key}
            label={it.label}
            body={it.body}
            chars={it.chars}
            injectKind={it.injectKind}
          />
        ))}
      </div>
    </details>
  );
});
