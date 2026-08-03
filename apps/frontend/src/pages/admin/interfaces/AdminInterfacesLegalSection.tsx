import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

const JURISDICTIONS = ["none", "de", "en", "custom"] as const;

export function AdminInterfacesLegalSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();

  const showPages =
    s.legalEnabled && s.legalJurisdiction !== "none";

  return (
    <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
      <h2 className="text-sm font-medium text-white">{t("admin:ifPlatformLegalTitle")}</h2>
      <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformLegalIntro")}</p>
      <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformLegalAvvHint")}</p>

      <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
        <input
          type="checkbox"
          className="rounded border-surface-border"
          checked={s.legalEnabled}
          onChange={(e) => s.setLegalEnabled(e.target.checked)}
        />
        {t("admin:ifPlatformLegalEnabled")}
      </label>

      <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-jurisdiction">
        {t("admin:ifPlatformLegalJurisdiction")}
      </label>
      <select
        id="legal-jurisdiction"
        className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
        value={s.legalJurisdiction}
        onChange={(e) => s.setLegalJurisdiction(e.target.value)}
      >
        {JURISDICTIONS.map((j) => (
          <option key={j} value={j}>
            {t(`admin:ifPlatformLegalJurisdiction_${j}`)}
          </option>
        ))}
      </select>
      <p className="mt-1 text-[11px] text-surface-muted">{t("admin:ifPlatformLegalJurisdictionHint")}</p>

      <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
        <input
          type="checkbox"
          className="rounded border-surface-border"
          checked={s.legalTermsEnabled}
          onChange={(e) => s.setLegalTermsEnabled(e.target.checked)}
          disabled={!s.legalEnabled || s.legalJurisdiction === "none"}
        />
        {t("admin:ifPlatformLegalTermsEnabled")}
      </label>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <label className="block text-xs text-surface-muted" htmlFor="legal-entity-name">
          {t("admin:ifPlatformLegalEntityName")}
          <input
            id="legal-entity-name"
            className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={s.legalEntityName}
            onChange={(e) => s.setLegalEntityName(e.target.value)}
            placeholder={t("admin:ifPlatformLegalEntityNamePlaceholder")}
          />
        </label>
        <label className="block text-xs text-surface-muted" htmlFor="legal-entity-email">
          {t("admin:ifPlatformLegalEntityEmail")}
          <input
            id="legal-entity-email"
            type="email"
            className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={s.legalEntityEmail}
            onChange={(e) => s.setLegalEntityEmail(e.target.value)}
            placeholder={t("admin:ifPlatformLegalEntityEmailPlaceholder")}
          />
        </label>
      </div>

      <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-entity-address">
        {t("admin:ifPlatformLegalEntityAddress")}
        <textarea
          id="legal-entity-address"
          rows={2}
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={s.legalEntityAddress}
          onChange={(e) => s.setLegalEntityAddress(e.target.value)}
          placeholder={t("admin:ifPlatformLegalEntityAddressPlaceholder")}
        />
      </label>

      <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-entity-phone">
        {t("admin:ifPlatformLegalEntityPhone")}
        <input
          id="legal-entity-phone"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={s.legalEntityPhone}
          onChange={(e) => s.setLegalEntityPhone(e.target.value)}
        />
      </label>

      <details className="mt-6 rounded-lg border border-white/10 bg-black/15 p-4">
        <summary className="cursor-pointer text-xs font-medium text-white">
          {t("admin:ifPlatformLegalOverridesTitle")}
        </summary>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifPlatformLegalOverridesIntro")}</p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-impressum-md">
          {t("admin:ifPlatformLegalImpressumOverride")}
          <textarea
            id="legal-impressum-md"
            rows={6}
            className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-xs text-white"
            value={s.legalImpressumMd}
            onChange={(e) => s.setLegalImpressumMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-privacy-md">
          {t("admin:ifPlatformLegalPrivacyOverride")}
          <textarea
            id="legal-privacy-md"
            rows={8}
            className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-xs text-white"
            value={s.legalPrivacyMd}
            onChange={(e) => s.setLegalPrivacyMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="legal-terms-md">
          {t("admin:ifPlatformLegalTermsOverride")}
          <textarea
            id="legal-terms-md"
            rows={8}
            className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-xs text-white"
            value={s.legalTermsMd}
            onChange={(e) => s.setLegalTermsMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
      </details>

      {showPages ? (
        <div className="mt-4 flex flex-wrap gap-3 text-xs">
          <Link to="/legal/impressum" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
            {t("admin:ifPlatformLegalPreviewImpressum")}
          </Link>
          <Link to="/legal/privacy" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
            {t("admin:ifPlatformLegalPreviewPrivacy")}
          </Link>
          {s.legalTermsEnabled ? (
            <Link to="/legal/terms" className="text-sky-400 hover:underline" target="_blank" rel="noopener noreferrer">
              {t("admin:ifPlatformLegalPreviewTerms")}
            </Link>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
