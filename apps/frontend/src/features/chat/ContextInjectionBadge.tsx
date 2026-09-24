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
    <details className="mb-base group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-snug rounded-tile border border-amber-500/35 bg-amber-950/35 px-base py-tight text-meta font-medium text-amber-100/90 marker:content-none [&::-webkit-details-marker]:hidden hover:bg-amber-950/50">
        <span className="relative flex h-1.5 w-1.5 shrink-0" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-pill bg-amber-400/80 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-pill bg-amber-300" />
        </span>
        <span className="max-w-chipWide truncate">{title}</span>
        {count > 0 ? (
          <span
            className="text-meta font-normal text-amber-200/55"
            title={t("chat:contextInjectTokensHint")}
          >
            {t("chat:contextInjectBudget", { chars: count, tokens })}
          </span>
        ) : null}
        <span className="text-meta font-normal text-amber-200/55 group-open:hidden">
          {t("chat:contextInjectExpandHint")}
        </span>
        <span className="hidden text-meta font-normal text-amber-200/55 group-open:inline">
          {t("chat:contextInjectCollapseHint")}
        </span>
      </summary>
      {trimmed ? (
        <pre className="mt-base max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-line-subtle bg-black/30 px-soft py-base font-sans text-xs leading-relaxed text-ink-muted">
          {trimmed}
        </pre>
      ) : (
        <p className="mt-base text-xs text-ink-muted">{t("chat:contextInjectEmptyBody")}</p>
      )}
    </details>
  );
});
