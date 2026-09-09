import { memo } from "react";
import { useTranslation } from "react-i18next";
import {
  approxTokensFromChars,
  injectItemCharCount,
} from "./contextInjectBudget";

export type ContextInjectionBadgeProps = {
  label: string;
  body?: string;
  chars?: number;
  injectKind?: string;
};

/** Collapsed badge for injected system context (AGENTS.md, system prompt, skills, …). */
export const ContextInjectionBadge = memo(function ContextInjectionBadge({
  label,
  body,
  chars,
  injectKind,
}: ContextInjectionBadgeProps) {
  const { t } = useTranslation(["chat"]);
  const trimmed = (body ?? "").trim();
  const count = injectItemCharCount({ chars, body });
  const tokens = approxTokensFromChars(count);
  const title = label.trim() || injectKind || t("chat:contextInjectFallback");

  return (
    <details className="mb-2 group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md border border-amber-500/35 bg-amber-950/35 px-2 py-1 text-[11px] font-medium text-amber-100/90 marker:content-none [&::-webkit-details-marker]:hidden hover:bg-amber-950/50">
        <span className="relative flex h-1.5 w-1.5 shrink-0" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-amber-400/80 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-300" />
        </span>
        <span className="max-w-[16rem] truncate">{title}</span>
        {count > 0 ? (
          <span
            className="text-[10px] font-normal text-amber-200/55"
            title={t("chat:contextInjectTokensHint")}
          >
            {t("chat:contextInjectBudget", { chars: count, tokens })}
          </span>
        ) : null}
        <span className="text-[10px] font-normal text-amber-200/55 group-open:hidden">
          {t("chat:contextInjectExpandHint")}
        </span>
        <span className="hidden text-[10px] font-normal text-amber-200/55 group-open:inline">
          {t("chat:contextInjectCollapseHint")}
        </span>
      </summary>
      {trimmed ? (
        <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-white/5 bg-black/30 px-3 py-2 font-sans text-xs leading-relaxed text-neutral-400">
          {trimmed}
        </pre>
      ) : (
        <p className="mt-2 text-xs text-neutral-500">{t("chat:contextInjectEmptyBody")}</p>
      )}
    </details>
  );
});
