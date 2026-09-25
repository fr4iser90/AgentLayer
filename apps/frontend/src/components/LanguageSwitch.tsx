import { useTranslation } from "react-i18next";
import { SUPPORTED } from "../i18n/config";

/**
 * Language control in the header chrome.
 *
 * It used to live inside the `UserMenu` dropdown and, for the signed-out login
 * screen, as a separate inline copy in `AppLayout`. Both meant the same thing —
 * a control you had to know about — and neither existed on `/admin` or `/org`,
 * which had no user menu at all, so an operator who could not read the language
 * they were shown had no way out of those pages.
 */
export function LanguageSwitch({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <div
      className={["flex items-center gap-hair", className ?? ""].join(" ")}
      role="group"
      aria-label={t("language.label")}
    >
      {SUPPORTED.map((lng) => {
        const active = i18n.resolvedLanguage?.startsWith(lng) ?? i18n.language.startsWith(lng);
        return (
          <button
            key={lng}
            type="button"
            aria-pressed={active}
            className={[
              "rounded-tile px-snug py-tight text-meta font-medium transition-colors",
              active
                ? "bg-white/15 text-ink-primary"
                : "text-ink-muted hover:bg-white/5 hover:text-ink-secondary"
            ].join(" ")}
            onClick={() => void i18n.changeLanguage(lng)}
          >
            {lng.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}