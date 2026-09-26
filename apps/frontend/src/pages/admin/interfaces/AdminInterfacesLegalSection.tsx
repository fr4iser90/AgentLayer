import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { Select, TextArea, TextInput } from "../../../ui/Field";

const JURISDICTIONS = ["none", "de", "en", "custom"] as const;

export function AdminInterfacesLegalSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();

  const showPages =
    s.legalEnabled && s.legalJurisdiction !== "none";

  return (
    <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
      <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifPlatformLegalTitle")}</h2>
      <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformLegalIntro")}</p>
      <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformLegalAvvHint")}</p>

      <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
        <input
          type="checkbox"
          className="rounded-tile border-line"
          checked={s.legalEnabled}
          onChange={(e) => s.setLegalEnabled(e.target.checked)}
        />
        {t("admin:ifPlatformLegalEnabled")}
      </label>

      <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-jurisdiction">
        {t("admin:ifPlatformLegalJurisdiction")}
      </label>
      <Select
        id="legal-jurisdiction"
        className="mt-tight max-w-controlWide"
        value={s.legalJurisdiction}
        onChange={(e) => s.setLegalJurisdiction(e.target.value)}
      >
        {JURISDICTIONS.map((j) => (
          <option key={j} value={j}>
            {t(`admin:ifPlatformLegalJurisdiction_${j}`)}
          </option>
        ))}
      </Select>
      <p className="mt-tight text-meta text-ink-muted">{t("admin:ifPlatformLegalJurisdictionHint")}</p>

      <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
        <input
          type="checkbox"
          className="rounded-tile border-line"
          checked={s.legalTermsEnabled}
          onChange={(e) => s.setLegalTermsEnabled(e.target.checked)}
          disabled={!s.legalEnabled || s.legalJurisdiction === "none"}
        />
        {t("admin:ifPlatformLegalTermsEnabled")}
      </label>

      <div className="mt-broad grid gap-wide sm:grid-cols-2">
        <label className="block text-xs text-ink-muted" htmlFor="legal-entity-name">
          {t("admin:ifPlatformLegalEntityName")}
          <TextInput
            id="legal-entity-name"
            className="mt-tight"
            value={s.legalEntityName}
            onChange={(e) => s.setLegalEntityName(e.target.value)}
            placeholder={t("admin:ifPlatformLegalEntityNamePlaceholder")}
          />
        </label>
        <label className="block text-xs text-ink-muted" htmlFor="legal-entity-email">
          {t("admin:ifPlatformLegalEntityEmail")}
          <TextInput
            id="legal-entity-email"
            type="email"
            className="mt-tight"
            value={s.legalEntityEmail}
            onChange={(e) => s.setLegalEntityEmail(e.target.value)}
            placeholder={t("admin:ifPlatformLegalEntityEmailPlaceholder")}
          />
        </label>
      </div>

      <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-entity-address">
        {t("admin:ifPlatformLegalEntityAddress")}
        <TextArea
          id="legal-entity-address"
          rows={2}
          className="mt-tight"
          value={s.legalEntityAddress}
          onChange={(e) => s.setLegalEntityAddress(e.target.value)}
          placeholder={t("admin:ifPlatformLegalEntityAddressPlaceholder")}
        />
      </label>

      <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-entity-phone">
        {t("admin:ifPlatformLegalEntityPhone")}
        <TextInput
          id="legal-entity-phone"
          className="mt-tight max-w-controlWide"
          value={s.legalEntityPhone}
          onChange={(e) => s.setLegalEntityPhone(e.target.value)}
        />
      </label>

      <details className="mt-broad rounded-card border border-line bg-black/15 p-wide">
        <summary className="cursor-pointer text-xs font-medium text-ink-primary">
          {t("admin:ifPlatformLegalOverridesTitle")}
        </summary>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifPlatformLegalOverridesIntro")}</p>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-impressum-md">
          {t("admin:ifPlatformLegalImpressumOverride")}
          <TextArea
            mono
            id="legal-impressum-md"
            rows={6}
            className="mt-tight text-xs"
            value={s.legalImpressumMd}
            onChange={(e) => s.setLegalImpressumMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-privacy-md">
          {t("admin:ifPlatformLegalPrivacyOverride")}
          <TextArea
            mono
            id="legal-privacy-md"
            rows={8}
            className="mt-tight text-xs"
            value={s.legalPrivacyMd}
            onChange={(e) => s.setLegalPrivacyMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="legal-terms-md">
          {t("admin:ifPlatformLegalTermsOverride")}
          <TextArea
            mono
            id="legal-terms-md"
            rows={8}
            className="mt-tight text-xs"
            value={s.legalTermsMd}
            onChange={(e) => s.setLegalTermsMd(e.target.value)}
            placeholder={t("admin:ifPlatformLegalOverridePlaceholder")}
          />
        </label>
      </details>

      {showPages ? (
        <div className="mt-wide flex flex-wrap gap-soft text-xs">
          <Link to="/legal/impressum" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">
            {t("admin:ifPlatformLegalPreviewImpressum")}
          </Link>
          <Link to="/legal/privacy" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">
            {t("admin:ifPlatformLegalPreviewPrivacy")}
          </Link>
          {s.legalTermsEnabled ? (
            <Link to="/legal/terms" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">
              {t("admin:ifPlatformLegalPreviewTerms")}
            </Link>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
