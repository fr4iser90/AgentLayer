import { memo } from "react";
import { useTranslation } from "react-i18next";
import { Disclosure } from "../../ui/Disclosure";
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
    <Disclosure
      className="mb-base"
      variant="chip"
      tone="warning"
      leading={
        <span className="relative flex h-1.5 w-1.5 shrink-0" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-pill bg-warning opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-pill bg-warning" />
        </span>
      }
      title={<span className="max-w-chipWide truncate">{title}</span>}
      meta={
        count > 0 ? (
          <span title={t("chat:contextInjectTokensHint")}>
            {t("chat:contextInjectBudget", { chars: count, tokens })}
          </span>
        ) : null
      }
      hint={{ open: t("chat:contextInjectExpandHint"), closed: t("chat:contextInjectCollapseHint") }}
    >
      {trimmed ? (
        <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-tile border border-line-subtle bg-black/30 px-soft py-base font-sans text-label leading-relaxed text-ink-muted">
          {trimmed}
        </pre>
      ) : (
        <p className="text-label text-ink-muted">{t("chat:contextInjectEmptyBody")}</p>
      )}
    </Disclosure>
  );
});
