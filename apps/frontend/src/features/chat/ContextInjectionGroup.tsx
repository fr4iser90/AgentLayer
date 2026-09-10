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
    <details className="mb-3 group">
      <summary className="inline-flex max-w-full cursor-pointer list-none flex-wrap items-center gap-1.5 rounded-md border border-amber-500/35 bg-amber-950/35 px-2.5 py-1.5 text-[11px] font-medium text-amber-100/90 marker:content-none [&::-webkit-details-marker]:hidden hover:bg-amber-950/50">
        <span className="relative flex h-1.5 w-1.5 shrink-0" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-amber-400/80 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-300" />
        </span>
        <span>{t("chat:contextInjectGroupTitle", { count: items.length })}</span>
        {totalChars > 0 ? (
          <span
            className="text-[10px] font-normal text-amber-200/55"
            title={t("chat:contextInjectTokensHint")}
          >
            {t("chat:contextInjectBudget", {
              chars: totalChars,
              tokens: totalTokens,
            })}
          </span>
        ) : null}
        {highlight.length > 0 ? (
          <span className="max-w-[18rem] truncate text-[10px] font-normal text-amber-200/65">
            {highlight.join(" · ")}
            {more > 0 ? ` · +${more}` : ""}
          </span>
        ) : null}
        <span className="text-[10px] font-normal text-amber-200/55 group-open:hidden">
          {t("chat:contextInjectExpandHint")}
        </span>
        <span className="hidden text-[10px] font-normal text-amber-200/55 group-open:inline">
          {t("chat:contextInjectCollapseHint")}
        </span>
      </summary>
      <div className="mt-2 flex flex-col gap-1 border-l border-amber-500/20 pl-2">
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
