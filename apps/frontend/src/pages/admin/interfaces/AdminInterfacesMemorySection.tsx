import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { envProviderPatternFromCleanupKeys } from "../../../features/admin/operatorSettings/operatorSettingsTypes";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Select, TextInput } from "../../../ui/Field";
import { Button } from "../../../ui/Button";

function ProviderModelSelect({
  id,
  value,
  models,
  loading,
  onChange,
  placeholder,
  loadingLabel,
}: {
  id: string;
  value: string;
  models: string[];
  loading?: boolean;
  onChange: (value: string) => void;
  placeholder: string;
  loadingLabel: string;
}) {
  const current = value.trim();
  const options = current && !models.includes(current) ? [current, ...models] : models;
  return (
    <Select
      id={id}
      className="mt-tight"
      value={current}
      disabled={loading || options.length === 0}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{loading ? loadingLabel : placeholder}</option>
      {options.map((model) => (
        <option key={model} value={model}>
          {model}
        </option>
      ))}
    </Select>
  );
}

export function AdminInterfacesMemorySection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();

  const embedModelsOk = s.ragEmbeddingModelOptions.length > 0;
  const embeddingProviderId = s.ragEmbeddingProviderId || s.ragEmbeddingProviderIdEffective || "";
  const extractorProviderId = s.extractorProviderId || s.extractorProviderIdEffective || "";
  const embeddingModelsKey = s.operatorProviderModelKey("embedding", embeddingProviderId);
  const extractorModelsKey = s.operatorProviderModelKey("extractor", extractorProviderId);
  const embeddingModelOptions = s.operatorProviderModelOptions[embeddingModelsKey] ?? [];
  const extractorModelOptions = s.operatorProviderModelOptions[extractorModelsKey] ?? [];

  useEffect(() => {
    if (embeddingProviderId) void s.loadOperatorProviderModels("embedding", embeddingProviderId);
  }, [embeddingProviderId, s.loadOperatorProviderModels]);

  useEffect(() => {
    if (extractorProviderId) void s.loadOperatorProviderModels("extractor", extractorProviderId);
  }, [extractorProviderId, s.loadOperatorProviderModels]);

  if (s.loading) {
    return <p className="text-sm text-ink-muted">{t("admin:loading")}</p>;
  }

  const pendingEmbeddingEnvProviders = (s.envOperatorProviders.embedding ?? []).filter((p) => !p.already_in_db);
  const pendingExtractorEnvProviders = (s.envOperatorProviders.extractor ?? []).filter((p) => !p.already_in_db);
  const operatorMetadataByKind = new Map(s.operatorProviderKindMetadata.map((metadata) => [metadata.kind, metadata]));
  const pendingEmbeddingEnvPrefix =
    operatorMetadataByKind.get("embedding")?.env_prefix_pattern ??
    envProviderPatternFromCleanupKeys(pendingEmbeddingEnvProviders[0]?.cleanup_keys);
  const pendingExtractorEnvPrefix =
    operatorMetadataByKind.get("extractor")?.env_prefix_pattern ??
    envProviderPatternFromCleanupKeys(pendingExtractorEnvProviders[0]?.cleanup_keys);

  return (
    <>
      <section className="rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifMemEmbedTitle")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifMemEmbedIntro")}</p>
        {pendingEmbeddingEnvProviders.length > 0 ? (
          <div className="mt-wide rounded-card border border-warning/25 bg-warning-subtle p-wide">
            <div className="flex flex-col gap-soft sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-sm font-medium text-badge-warning">
                  {t("admin:envProviderFoundTitle", { count: pendingEmbeddingEnvProviders.length })}
                </h3>
                <p className="mt-tight text-xs text-badge-warning">
                  {t("admin:envProviderFoundIntro", { prefix: pendingEmbeddingEnvPrefix })}
                </p>
              </div>
              <Button
                variant="primary"
                tone="warning"
                type="button"
                disabled={s.envOperatorImporting === "embedding"}
                className="px-soft py-snug text-sm text-black"
                onClick={() => void s.importOperatorEnvProviders("embedding")}
              >
                {s.envOperatorImporting === "embedding" ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
              </Button>
            </div>
            <div className="mt-soft space-y-base">
              {pendingEmbeddingEnvProviders.map((p) => (
                <details key={p.provider_id} className="rounded-tile border border-line bg-black/25 p-soft">
                  <summary className="cursor-pointer text-xs text-badge-warning">
                    <span className="font-mono">{p.provider_id}</span> · {p.label}
                    {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                  </summary>
                  <p className="mt-base break-all font-mono text-meta text-ink-muted">{p.base_url}</p>
                  <p className="mt-tight text-meta text-ink-secondary">
                    {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                  </p>
                  <p className="mt-tight text-meta text-ink-secondary">
                    {t("admin:envLlmKey")}:{" "}
                    {p.api_key_configured
                      ? t("admin:envLlmKeyRedacted", { last4: p.api_key_last4 ?? t("admin:envLlmKeyLast4Unknown") })
                      : t("admin:envLlmKeyEmpty")}
                  </p>
                  <ul className="mt-base grid gap-tight sm:grid-cols-2">
                    {p.cleanup_keys.map((key) => (
                      <li key={key} className="font-mono text-meta text-badge-warning">{key}</li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
            {s.envOperatorCleanupNotes.embedding ? (
              <p className="mt-soft text-xs text-badge-warning">{s.envOperatorCleanupNotes.embedding}</p>
            ) : null}
          </div>
        ) : null}
        <div className="mt-wide flex flex-wrap gap-base">
          <Button
            variant="primary"
            type="button"
            className="border-accent/40 px-soft py-snug text-sm text-badge-accent"
            disabled={s.embeddingModelsLoading}
            onClick={() => void s.refreshEmbeddingCatalog()}
          >
            {s.embeddingModelsLoading ? t("admin:ifMemLoadingModels") : t("admin:ifMemLoadModelsEmbedding")}
          </Button>
        </div>
        {s.ragEmbeddingStatusHint ? (
          <p
            className={`mt-base text-xs ${
              embedModelsOk ? "text-success" : "text-badge-warning"
            }`}
          >
            {s.ragEmbeddingStatusHint}
          </p>
        ) : null}
        <datalist id="embed-model-ids">
          {s.ragEmbeddingModelOptions.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>

        <div className="mt-broad space-y-broad">
            <div className="rounded-card border border-line bg-black/15 p-wide">
              <div className="flex flex-wrap items-center justify-between gap-base">
                <span className="text-xs font-medium text-ink-muted">{t("admin:ifMemEndpointN", { n: 1 })}</span>
                {s.embeddingApiBaseSource === "env" ? (
                  <span className="text-xs text-badge-warning">{t("admin:ifMemBaseUrlFromEnv")}</span>
                ) : s.embeddingApiBaseEffective ? (
                  <span className="font-mono text-xs text-ink-muted">{t("admin:ifMemActive")}</span>
                ) : null}
              </div>
              {s.embeddingProviders.length > 0 ? (
                <>
                  <label className="mt-base block text-xs text-ink-muted" htmlFor="embedding-provider-id">
                    {t("admin:ifMemEmbeddingProvider")}
                  </label>
                  <Select
                    id="embedding-provider-id"
                    className="mt-tight max-w-controlWide"
                    value={s.ragEmbeddingProviderId || s.ragEmbeddingProviderIdEffective || ""}
                    onChange={(e) => s.setRagEmbeddingProviderId(e.target.value)}
                  >
                    <option value="">{t("admin:ifMemEmbeddingProviderAuto")}</option>
                    {s.embeddingProviders.map((p) => (
                      <option key={p.provider_id} value={p.provider_id}>
                        {p.label} ({p.provider_id})
                      </option>
                    ))}
                  </Select>
                  {s.ragEmbeddingProviderIdEffective ? (
                    <p className="mt-tight text-xs text-ink-muted">
                      {t("admin:ifMemEmbeddingProviderActive")}{" "}
                      <span className="font-mono text-ink-secondary">{s.ragEmbeddingProviderIdEffective}</span>
                      {!s.ragEmbeddingProviderId && s.ragEmbeddingProviderIdEffective
                        ? ` (${t("admin:ifMemEmbeddingProviderAuto")})`
                        : null}
                    </p>
                  ) : null}
                </>
              ) : null}
            <label className="mt-base block text-xs text-ink-muted" htmlFor="embedding-base-url">
              {t("admin:ifMemBaseUrlLabel")}
            </label>
            <TextInput
              mono
              id="embedding-base-url"
              className="mt-tight"
              value={
                s.embeddingApiBaseSource === "env"
                  ? (s.embeddingApiBaseEffective ?? "")
                  : s.embeddingApiBaseUrl
              }
              onChange={(e) => s.setEmbeddingApiBaseUrl(e.target.value)}
              placeholder={t("admin:ifMemoryEmbedUrlPlaceholder")}
              autoComplete="off"
              disabled={s.embeddingApiBaseSource === "env"}
            />
            {s.embeddingApiBaseSource === "env" ? (
              <p className="mt-tight text-xs text-ink-muted">
                <span className="font-mono">EMBEDDING_PROVIDER_1_BASE_URL</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span>{" "}
                {t("admin:ifMemEnvOverridesDbUrl")}
              </p>
            ) : s.embeddingApiBaseEffective ? (
              <p className="mt-tight text-xs text-ink-muted">
                {t("admin:ifMemEffectiveAfterSave")}{" "}
                <span className="font-mono text-ink-secondary">{s.embeddingApiBaseEffective}</span>
              </p>
            ) : null}
            <p className="mt-soft text-xs text-ink-muted">
              {t("admin:ifMemKeyLabel")}{" "}
              {s.embeddingApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
              {s.embeddingApiKeySource === "env" ? (
                <span className="text-badge-warning"> {t("admin:ifMemFromEnv")}</span>
              ) : null}
            </p>
            <label className="mt-base block text-xs text-ink-muted" htmlFor="embedding-api-key">
              {t("admin:ifMemApiKeyLabel")}
            </label>
            <TextInput
              mono
              id="embedding-api-key"
              type="password"
              autoComplete="off"
              className="mt-tight"
              value={s.embeddingApiKey}
              onChange={(e) => s.setEmbeddingApiKey(e.target.value)}
              placeholder={
                s.embeddingApiKeyConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:ifMemPasteKey")
              }
              disabled={s.embeddingApiKeySource === "env"}
            />
            {s.embeddingApiKeySource === "env" ? (
              <p className="mt-tight text-xs text-ink-muted">
                <span className="font-mono">EMBEDDING_API_HEADER_VALUE</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span>{" "}
                {t("admin:ifMemEnvOverridesDbKey")}
              </p>
            ) : null}
            <label className="mt-soft block text-xs text-ink-muted" htmlFor="embedding-header-name">
              {t("admin:ifMemHeaderForKey")}
            </label>
            <TextInput
              mono
              id="embedding-header-name"
              className="mt-tight max-w-controlWide"
              value={s.embeddingApiHeaderName}
              onChange={(e) => s.setEmbeddingApiHeaderName(e.target.value)}
              placeholder={t("admin:ifMemoryApiKeyPlaceholder")}
              autoComplete="off"
              disabled={s.embeddingApiKeySource === "env"}
            />
            <p className="mt-tight text-xs text-ink-muted">
              {t("admin:ifMemEffective")}{" "}
              <span className="font-mono text-ink-secondary">{s.embeddingApiHeaderNameEffective}</span>
              {s.embeddingApiHeaderNameSource === "env" ? ` ${t("admin:ifMemFromEnv")}` : ""}.{" "}
              {t("admin:ifMemAuthBearerAuto")}
            </p>
            <h4 className="mt-wide text-xs font-medium uppercase tracking-wide text-ink-muted">
              {t("admin:ifMemEmbedModelSection")}
            </h4>
            <div className="mt-base grid gap-soft sm:grid-cols-2">
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="rag-model">
                  {t("admin:ifMemModelId")}
                </label>
                <ProviderModelSelect
                  id="rag-model"
                  value={s.ragEmbeddingModel}
                  models={embeddingModelOptions}
                  loading={s.operatorProviderModelsLoading[embeddingModelsKey]}
                  onChange={(value) => s.setRagEmbeddingModel(value)}
                  placeholder={t("admin:ifMemoryModelFilePlaceholder")}
                  loadingLabel={t("admin:ifMemLoadingModels")}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="rag-dim">
                  {t("admin:ifMemEmbedDim")}
                </label>
                <TextInput
                  mono
                  id="rag-dim"
                  type="number"
                  min={32}
                  max={4096}
                  className="mt-tight"
                  value={s.ragEmbeddingDim}
                  onChange={(e) => s.setRagEmbeddingDim(e.target.value)}
                />
              </div>
            </div>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifMemSaveSyncHint")}</p>
          </div>
          <div className="rounded-card border border-line bg-black/15 p-wide">
            <div className="flex flex-wrap items-center justify-between gap-base">
              <span className="text-xs font-medium text-ink-muted">{t("admin:ifMemExtractorTitle")}</span>
              {s.extractorProviders.length > 0 ? (
                <span className="font-mono text-xs text-badge-success">{t("admin:ifMemConfigured")}</span>
              ) : (
                <span className="text-xs text-badge-warning">{t("admin:ifMemNotConfigured")}</span>
              )}
            </div>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifMemExtractorIntro")}</p>
            {pendingExtractorEnvProviders.length > 0 ? (
              <div className="mt-wide rounded-card border border-warning/25 bg-warning-subtle p-wide">
                <div className="flex flex-col gap-soft sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-badge-warning">
                      {t("admin:envProviderFoundTitle", { count: pendingExtractorEnvProviders.length })}
                    </h3>
                    <p className="mt-tight text-xs text-badge-warning">
                      {t("admin:envProviderFoundIntro", { prefix: pendingExtractorEnvPrefix })}
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    tone="warning"
                    type="button"
                    disabled={s.envOperatorImporting === "extractor"}
                    className="px-soft py-snug text-sm text-black"
                    onClick={() => void s.importOperatorEnvProviders("extractor")}
                  >
                    {s.envOperatorImporting === "extractor" ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
                  </Button>
                </div>
                <div className="mt-soft space-y-base">
                  {pendingExtractorEnvProviders.map((p) => (
                    <details key={p.provider_id} className="rounded-tile border border-line bg-black/25 p-soft">
                      <summary className="cursor-pointer text-xs text-badge-warning">
                        <span className="font-mono">{p.provider_id}</span> · {p.label}
                        {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                      </summary>
                      <p className="mt-base break-all font-mono text-meta text-ink-muted">{p.base_url}</p>
                      <p className="mt-tight text-meta text-ink-secondary">
                        {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                      </p>
                      <ul className="mt-base grid gap-tight sm:grid-cols-2">
                        {p.cleanup_keys.map((key) => (
                          <li key={key} className="font-mono text-meta text-badge-warning">{key}</li>
                        ))}
                      </ul>
                    </details>
                  ))}
                </div>
              </div>
            ) : null}
            {s.extractorProviders.length > 0 ? (
              <>
                <label className="mt-soft block text-xs text-ink-muted" htmlFor="extractor-provider-id">
                  {t("admin:ifMemExtractorProvider")}
                </label>
                <Select
                  id="extractor-provider-id"
                  className="mt-tight max-w-controlWide"
                  value={s.extractorProviderId || s.extractorProviderIdEffective || ""}
                  onChange={(e) => s.setExtractorProviderId(e.target.value)}
                >
                  <option value="">{t("admin:ifMemExtractorProviderAuto")}</option>
                  {s.extractorProviders.map((p) => (
                    <option key={p.provider_id} value={p.provider_id}>
                      {p.label} ({p.provider_id})
                    </option>
                  ))}
                </Select>
                {s.extractorProviderIdEffective ? (
                  <p className="mt-tight text-xs text-ink-muted">
                    {t("admin:ifMemExtractorProviderActive")}{" "}
                    <span className="font-mono text-ink-secondary">{s.extractorProviderIdEffective}</span>
                    {!s.extractorProviderId && s.extractorProviderIdEffective
                      ? ` (${t("admin:ifMemExtractorProviderAuto")})`
                      : null}
                  </p>
                ) : null}
              </>
            ) : null}
            <h4 className="mt-wide text-xs font-medium uppercase tracking-wide text-ink-muted">
              {t("admin:ifMemExtractorAdminProvider")}
            </h4>
            <label className="mt-base block text-xs text-ink-muted" htmlFor="extractor-base-url">
              {t("admin:ifMemBaseUrlLabel")}
            </label>
            <TextInput
              mono
              id="extractor-base-url"
              className="mt-tight"
              value={s.extractorApiBaseUrl}
              onChange={(e) => s.setExtractorApiBaseUrl(e.target.value)}
              placeholder={t("admin:ifMemExtractorUrlPlaceholder")}
              autoComplete="off"
            />
            {s.extractorApiBaseEffective ? (
              <p className="mt-tight text-xs text-ink-muted">
                {t("admin:ifMemEffectiveAfterSave")}{" "}
                <span className="font-mono text-ink-secondary">{s.extractorApiBaseEffective}</span>
              </p>
            ) : (
              <p className="mt-tight text-xs text-ink-muted">
                <span className="font-mono">EXTRACTOR_PROVIDER_1_BASE_URL</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span> {t("admin:ifMemExtractorEnvAlternative")}
              </p>
            )}
            <p className="mt-soft text-xs text-ink-muted">
              {t("admin:ifMemKeyLabel")}{" "}
              {s.extractorApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
            </p>
            <label className="mt-base block text-xs text-ink-muted" htmlFor="extractor-api-key">
              {t("admin:ifMemApiKeyLabel")}
            </label>
            <TextInput
              mono
              id="extractor-api-key"
              type="password"
              autoComplete="off"
              className="mt-tight"
              value={s.extractorApiKey}
              onChange={(e) => s.setExtractorApiKey(e.target.value)}
              placeholder={s.extractorApiKeyConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:ifMemPasteKey")}
            />
            <div className="mt-soft grid gap-soft sm:grid-cols-3">
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="extractor-header-name">
                  {t("admin:ifMemHeaderForKey")}
                </label>
                <TextInput
                  mono
                  id="extractor-header-name"
                  className="mt-tight"
                  value={s.extractorApiHeaderName}
                  onChange={(e) => s.setExtractorApiHeaderName(e.target.value)}
                  placeholder={t("admin:ifMemoryApiKeyPlaceholder")}
                  autoComplete="off"
                />
                <p className="mt-tight text-xs text-ink-muted">
                  {t("admin:ifMemEffective")}{" "}
                  <span className="font-mono text-ink-secondary">{s.extractorApiHeaderNameEffective}</span>
                </p>
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="extractor-model">
                  {t("admin:ifMemExtractorModel")}
                </label>
                <ProviderModelSelect
                  id="extractor-model"
                  value={s.extractorModel}
                  models={extractorModelOptions}
                  loading={s.operatorProviderModelsLoading[extractorModelsKey]}
                  onChange={(value) => s.setExtractorModel(value)}
                  placeholder={t("admin:ifMemExtractorModelPlaceholder")}
                  loadingLabel={t("admin:ifMemLoadingModels")}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="extractor-timeout">
                  {t("admin:ifMemExtractorTimeout")}
                </label>
                <TextInput
                  mono
                  id="extractor-timeout"
                  type="number"
                  min={1}
                  max={1800}
                  className="mt-tight"
                  value={s.extractorTimeoutSec}
                  onChange={(e) => s.setExtractorTimeoutSec(e.target.value)}
                />
              </div>
            </div>
            <p className="mt-soft text-xs text-ink-muted">
              {t("admin:ifMemExtractorHarnessHint")}
            </p>
          </div>
        </div>
        {!s.embeddingApiBaseUrl.trim() && s.embeddingApiBaseSource !== "env" ? (
          <p className="mt-wide text-xs text-badge-warning">{t("admin:ifMemNoBaseUrl")}</p>
        ) : null}
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:memoryRagTitle")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifMemMemoryRagIntro")}</p>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.exposeInternalErrors}
            onChange={(e) => s.setExposeInternalErrors(e.target.checked)}
          />
          {t("admin:ifMemExposeErrors")}
        </label>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.memoryEnabled}
            onChange={(e) => s.setMemoryEnabled(e.target.checked)}
          />
          {t("admin:ifMemEnableMemory")}
        </label>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.ragEnabled}
            onChange={(e) => s.setRagEnabled(e.target.checked)}
          />
          {t("admin:ifMemEnableRag")}
        </label>
        <div className="mt-wide grid max-w-measure gap-soft sm:grid-cols-2">
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="rag-chunk">
              {t("admin:ifMemChunkSize")}
            </label>
            <TextInput
              mono
              id="rag-chunk"
              type="number"
              min={200}
              max={8000}
              className="mt-tight"
              value={s.ragChunkSize}
              onChange={(e) => s.setRagChunkSize(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="rag-overlap">
              {t("admin:ifMemChunkOverlap")}
            </label>
            <TextInput
              mono
              id="rag-overlap"
              type="number"
              min={0}
              max={2000}
              className="mt-tight"
              value={s.ragChunkOverlap}
              onChange={(e) => s.setRagChunkOverlap(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="rag-topk">
              {t("admin:ifMemTopK")}
            </label>
            <TextInput
              mono
              id="rag-topk"
              type="number"
              min={1}
              max={50}
              className="mt-tight"
              value={s.ragTopK}
              onChange={(e) => s.setRagTopK(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="rag-timeout">
              {t("admin:ifMemEmbedTimeout")}
            </label>
            <TextInput
              mono
              id="rag-timeout"
              type="number"
              min={5}
              max={600}
              step="1"
              className="mt-tight"
              value={s.ragEmbedTimeout}
              onChange={(e) => s.setRagEmbedTimeout(e.target.value)}
            />
          </div>
        </div>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="rag-domains">
          {t("admin:ifMemTenantDomains")}
        </label>
        <TextInput
          mono
          id="rag-domains"
          className="mt-tight"
          value={s.ragTenantDomains}
          onChange={(e) => s.setRagTenantDomains(e.target.value)}
          placeholder={t("admin:ifMemoryCollectionPlaceholder")}
        />
        {s.ragTenantEffective.length > 0 ? (
          <p className="mt-base text-xs text-ink-muted">
            {t("admin:ifMemEffectiveDomains")}{" "}
            <span className="font-mono text-ink-secondary">{s.ragTenantEffective.join(", ")}</span>
          </p>
        ) : null}
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="docs-root">
          {t("admin:ifMemDocsPathOptional")}
        </label>
        <TextInput
          mono
          id="docs-root"
          className="mt-tight"
          value={s.docsRoot}
          onChange={(e) => s.setDocsRoot(e.target.value)}
          placeholder={t("admin:ifMemoryDocsPathPlaceholder")}
          autoComplete="off"
        />
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifMemGraphTitle")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifMemGraphIntro")}</p>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.memGraphEnabled}
            onChange={(e) => s.setMemGraphEnabled(e.target.checked)}
          />
          {t("admin:ifMemGraphEnable")}
        </label>
        <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.memGraphLogActivations}
            onChange={(e) => s.setMemGraphLogActivations(e.target.checked)}
          />
          {t("admin:ifMemGraphLog")}
        </label>
        <div className="mt-wide grid max-w-measure gap-soft sm:grid-cols-2">
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="mg-hops">
              {t("admin:ifMemGraphMaxHops")}
            </label>
            <TextInput
              mono
              id="mg-hops"
              type="number"
              min={0}
              max={4}
              className="mt-tight"
              value={s.memGraphMaxHops}
              onChange={(e) => s.setMemGraphMaxHops(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="mg-score">
              {t("admin:ifMemGraphMinScore")}
            </label>
            <TextInput
              mono
              id="mg-score"
              type="number"
              step="0.01"
              min={0}
              max={1}
              className="mt-tight"
              value={s.memGraphMinScore}
              onChange={(e) => s.setMemGraphMinScore(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="mg-bullets">
              {t("admin:ifMemGraphMaxBullets")}
            </label>
            <TextInput
              mono
              id="mg-bullets"
              type="number"
              min={1}
              max={50}
              className="mt-tight"
              value={s.memGraphMaxBullets}
              onChange={(e) => s.setMemGraphMaxBullets(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted" htmlFor="mg-chars">
              {t("admin:ifMemGraphMaxChars")}
            </label>
            <TextInput
              mono
              id="mg-chars"
              type="number"
              min={200}
              max={50000}
              className="mt-tight"
              value={s.memGraphMaxPromptChars}
              onChange={(e) => s.setMemGraphMaxPromptChars(e.target.value)}
            />
          </div>
        </div>
      </section>
    </>
  );
}
