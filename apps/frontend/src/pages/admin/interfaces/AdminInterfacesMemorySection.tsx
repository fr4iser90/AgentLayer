import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { envProviderPatternFromCleanupKeys } from "../../../features/admin/operatorSettings/operatorSettingsTypes";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";

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
    <select
      id={id}
      className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
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
    </select>
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
    return <p className="text-sm text-surface-muted">{t("admin:loading")}</p>;
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
      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:ifMemEmbedTitle")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemEmbedIntro")}</p>
        {pendingEmbeddingEnvProviders.length > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-400/25 bg-amber-500/10 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-sm font-medium text-amber-100">
                  {t("admin:envProviderFoundTitle", { count: pendingEmbeddingEnvProviders.length })}
                </h3>
                <p className="mt-1 text-xs text-amber-100/75">
                  {t("admin:envProviderFoundIntro", { prefix: pendingEmbeddingEnvPrefix })}
                </p>
              </div>
              <button
                type="button"
                disabled={s.envOperatorImporting === "embedding"}
                className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50"
                onClick={() => void s.importOperatorEnvProviders("embedding")}
              >
                {s.envOperatorImporting === "embedding" ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {pendingEmbeddingEnvProviders.map((p) => (
                <details key={p.provider_id} className="rounded-md border border-white/10 bg-black/25 p-3">
                  <summary className="cursor-pointer text-xs text-amber-100">
                    <span className="font-mono">{p.provider_id}</span> · {p.label}
                    {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                  </summary>
                  <p className="mt-2 break-all font-mono text-[11px] text-surface-muted">{p.base_url}</p>
                  <p className="mt-1 text-[11px] text-neutral-300">
                    {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                  </p>
                  <p className="mt-1 text-[11px] text-neutral-300">
                    {t("admin:envLlmKey")}:{" "}
                    {p.api_key_configured
                      ? t("admin:envLlmKeyRedacted", { last4: p.api_key_last4 ?? t("admin:envLlmKeyLast4Unknown") })
                      : t("admin:envLlmKeyEmpty")}
                  </p>
                  <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                    {p.cleanup_keys.map((key) => (
                      <li key={key} className="font-mono text-[10px] text-amber-100/70">{key}</li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
            {s.envOperatorCleanupNotes.embedding ? (
              <p className="mt-3 text-xs text-amber-100/75">{s.envOperatorCleanupNotes.embedding}</p>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
            disabled={s.embeddingModelsLoading}
            onClick={() => void s.refreshEmbeddingCatalog()}
          >
            {s.embeddingModelsLoading ? t("admin:ifMemLoadingModels") : t("admin:ifMemLoadModelsEmbedding")}
          </button>
        </div>
        {s.ragEmbeddingStatusHint ? (
          <p
            className={`mt-2 text-xs ${
              embedModelsOk ? "text-emerald-400/90" : "text-amber-300/90"
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

        <div className="mt-6 space-y-6">
            <div className="rounded-lg border border-white/10 bg-black/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-surface-muted">{t("admin:ifMemEndpointN", { n: 1 })}</span>
                {s.embeddingApiBaseSource === "env" ? (
                  <span className="text-xs text-amber-300/90">{t("admin:ifMemBaseUrlFromEnv")}</span>
                ) : s.embeddingApiBaseEffective ? (
                  <span className="font-mono text-xs text-neutral-500">{t("admin:ifMemActive")}</span>
                ) : null}
              </div>
              {s.embeddingProviders.length > 0 ? (
                <>
                  <label className="mt-2 block text-xs text-surface-muted" htmlFor="embedding-provider-id">
                    {t("admin:ifMemEmbeddingProvider")}
                  </label>
                  <select
                    id="embedding-provider-id"
                    className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
                    value={s.ragEmbeddingProviderId || s.ragEmbeddingProviderIdEffective || ""}
                    onChange={(e) => s.setRagEmbeddingProviderId(e.target.value)}
                  >
                    <option value="">{t("admin:ifMemEmbeddingProviderAuto")}</option>
                    {s.embeddingProviders.map((p) => (
                      <option key={p.provider_id} value={p.provider_id}>
                        {p.label} ({p.provider_id})
                      </option>
                    ))}
                  </select>
                  {s.ragEmbeddingProviderIdEffective ? (
                    <p className="mt-1 text-xs text-surface-muted">
                      {t("admin:ifMemEmbeddingProviderActive")}{" "}
                      <span className="font-mono text-neutral-300">{s.ragEmbeddingProviderIdEffective}</span>
                      {!s.ragEmbeddingProviderId && s.ragEmbeddingProviderIdEffective
                        ? ` (${t("admin:ifMemEmbeddingProviderAuto")})`
                        : null}
                    </p>
                  ) : null}
                </>
              ) : null}
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="embedding-base-url">
              {t("admin:ifMemBaseUrlLabel")}
            </label>
            <input
              id="embedding-base-url"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
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
              <p className="mt-1 text-xs text-surface-muted">
                <span className="font-mono">EMBEDDING_PROVIDER_1_BASE_URL</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span>{" "}
                {t("admin:ifMemEnvOverridesDbUrl")}
              </p>
            ) : s.embeddingApiBaseEffective ? (
              <p className="mt-1 text-xs text-surface-muted">
                {t("admin:ifMemEffectiveAfterSave")}{" "}
                <span className="font-mono text-neutral-300">{s.embeddingApiBaseEffective}</span>
              </p>
            ) : null}
            <p className="mt-3 text-xs text-surface-muted">
              {t("admin:ifMemKeyLabel")}{" "}
              {s.embeddingApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
              {s.embeddingApiKeySource === "env" ? (
                <span className="text-amber-300/90"> {t("admin:ifMemFromEnv")}</span>
              ) : null}
            </p>
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="embedding-api-key">
              {t("admin:ifMemApiKeyLabel")}
            </label>
            <input
              id="embedding-api-key"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
              value={s.embeddingApiKey}
              onChange={(e) => s.setEmbeddingApiKey(e.target.value)}
              placeholder={
                s.embeddingApiKeyConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:ifMemPasteKey")
              }
              disabled={s.embeddingApiKeySource === "env"}
            />
            {s.embeddingApiKeySource === "env" ? (
              <p className="mt-1 text-xs text-surface-muted">
                <span className="font-mono">EMBEDDING_API_HEADER_VALUE</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span>{" "}
                {t("admin:ifMemEnvOverridesDbKey")}
              </p>
            ) : null}
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="embedding-header-name">
              {t("admin:ifMemHeaderForKey")}
            </label>
            <input
              id="embedding-header-name"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
              value={s.embeddingApiHeaderName}
              onChange={(e) => s.setEmbeddingApiHeaderName(e.target.value)}
              placeholder={t("admin:ifMemoryApiKeyPlaceholder")}
              autoComplete="off"
              disabled={s.embeddingApiKeySource === "env"}
            />
            <p className="mt-1 text-xs text-surface-muted">
              {t("admin:ifMemEffective")}{" "}
              <span className="font-mono text-neutral-300">{s.embeddingApiHeaderNameEffective}</span>
              {s.embeddingApiHeaderNameSource === "env" ? ` ${t("admin:ifMemFromEnv")}` : ""}.{" "}
              {t("admin:ifMemAuthBearerAuto")}
            </p>
            <h4 className="mt-4 text-xs font-medium uppercase tracking-wide text-surface-muted">
              {t("admin:ifMemEmbedModelSection")}
            </h4>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-model">
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
                <label className="block text-xs text-surface-muted" htmlFor="rag-dim">
                  {t("admin:ifMemEmbedDim")}
                </label>
                <input
                  id="rag-dim"
                  type="number"
                  min={32}
                  max={4096}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.ragEmbeddingDim}
                  onChange={(e) => s.setRagEmbeddingDim(e.target.value)}
                />
              </div>
            </div>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemSaveSyncHint")}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-medium text-surface-muted">{t("admin:ifMemExtractorTitle")}</span>
              {s.extractorProviders.length > 0 ? (
                <span className="font-mono text-xs text-emerald-300/90">{t("admin:ifMemConfigured")}</span>
              ) : (
                <span className="text-xs text-amber-300/90">{t("admin:ifMemNotConfigured")}</span>
              )}
            </div>
            <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemExtractorIntro")}</p>
            {pendingExtractorEnvProviders.length > 0 ? (
              <div className="mt-4 rounded-lg border border-amber-400/25 bg-amber-500/10 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-amber-100">
                      {t("admin:envProviderFoundTitle", { count: pendingExtractorEnvProviders.length })}
                    </h3>
                    <p className="mt-1 text-xs text-amber-100/75">
                      {t("admin:envProviderFoundIntro", { prefix: pendingExtractorEnvPrefix })}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={s.envOperatorImporting === "extractor"}
                    className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50"
                    onClick={() => void s.importOperatorEnvProviders("extractor")}
                  >
                    {s.envOperatorImporting === "extractor" ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {pendingExtractorEnvProviders.map((p) => (
                    <details key={p.provider_id} className="rounded-md border border-white/10 bg-black/25 p-3">
                      <summary className="cursor-pointer text-xs text-amber-100">
                        <span className="font-mono">{p.provider_id}</span> · {p.label}
                        {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                      </summary>
                      <p className="mt-2 break-all font-mono text-[11px] text-surface-muted">{p.base_url}</p>
                      <p className="mt-1 text-[11px] text-neutral-300">
                        {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                      </p>
                      <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                        {p.cleanup_keys.map((key) => (
                          <li key={key} className="font-mono text-[10px] text-amber-100/70">{key}</li>
                        ))}
                      </ul>
                    </details>
                  ))}
                </div>
              </div>
            ) : null}
            {s.extractorProviders.length > 0 ? (
              <>
                <label className="mt-3 block text-xs text-surface-muted" htmlFor="extractor-provider-id">
                  {t("admin:ifMemExtractorProvider")}
                </label>
                <select
                  id="extractor-provider-id"
                  className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.extractorProviderId || s.extractorProviderIdEffective || ""}
                  onChange={(e) => s.setExtractorProviderId(e.target.value)}
                >
                  <option value="">{t("admin:ifMemExtractorProviderAuto")}</option>
                  {s.extractorProviders.map((p) => (
                    <option key={p.provider_id} value={p.provider_id}>
                      {p.label} ({p.provider_id})
                    </option>
                  ))}
                </select>
                {s.extractorProviderIdEffective ? (
                  <p className="mt-1 text-xs text-surface-muted">
                    {t("admin:ifMemExtractorProviderActive")}{" "}
                    <span className="font-mono text-neutral-300">{s.extractorProviderIdEffective}</span>
                    {!s.extractorProviderId && s.extractorProviderIdEffective
                      ? ` (${t("admin:ifMemExtractorProviderAuto")})`
                      : null}
                  </p>
                ) : null}
              </>
            ) : null}
            <h4 className="mt-4 text-xs font-medium uppercase tracking-wide text-surface-muted">
              {t("admin:ifMemExtractorAdminProvider")}
            </h4>
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="extractor-base-url">
              {t("admin:ifMemBaseUrlLabel")}
            </label>
            <input
              id="extractor-base-url"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.extractorApiBaseUrl}
              onChange={(e) => s.setExtractorApiBaseUrl(e.target.value)}
              placeholder={t("admin:ifMemExtractorUrlPlaceholder")}
              autoComplete="off"
            />
            {s.extractorApiBaseEffective ? (
              <p className="mt-1 text-xs text-surface-muted">
                {t("admin:ifMemEffectiveAfterSave")}{" "}
                <span className="font-mono text-neutral-300">{s.extractorApiBaseEffective}</span>
              </p>
            ) : (
              <p className="mt-1 text-xs text-surface-muted">
                <span className="font-mono">EXTRACTOR_PROVIDER_1_BASE_URL</span> {t("admin:ifMemInDotenv")}{" "}
                <span className="font-mono">.env</span> {t("admin:ifMemExtractorEnvAlternative")}
              </p>
            )}
            <p className="mt-3 text-xs text-surface-muted">
              {t("admin:ifMemKeyLabel")}{" "}
              {s.extractorApiKeyConfigured ? t("admin:ifMemKeyStored") : t("admin:ifMemKeyEmpty")}
            </p>
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="extractor-api-key">
              {t("admin:ifMemApiKeyLabel")}
            </label>
            <input
              id="extractor-api-key"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.extractorApiKey}
              onChange={(e) => s.setExtractorApiKey(e.target.value)}
              placeholder={s.extractorApiKeyConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:ifMemPasteKey")}
            />
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="extractor-header-name">
                  {t("admin:ifMemHeaderForKey")}
                </label>
                <input
                  id="extractor-header-name"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.extractorApiHeaderName}
                  onChange={(e) => s.setExtractorApiHeaderName(e.target.value)}
                  placeholder={t("admin:ifMemoryApiKeyPlaceholder")}
                  autoComplete="off"
                />
                <p className="mt-1 text-xs text-surface-muted">
                  {t("admin:ifMemEffective")}{" "}
                  <span className="font-mono text-neutral-300">{s.extractorApiHeaderNameEffective}</span>
                </p>
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="extractor-model">
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
                <label className="block text-xs text-surface-muted" htmlFor="extractor-timeout">
                  {t("admin:ifMemExtractorTimeout")}
                </label>
                <input
                  id="extractor-timeout"
                  type="number"
                  min={1}
                  max={1800}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.extractorTimeoutSec}
                  onChange={(e) => s.setExtractorTimeoutSec(e.target.value)}
                />
              </div>
            </div>
            <p className="mt-3 text-xs text-surface-muted">
              {t("admin:ifMemExtractorHarnessHint")}
            </p>
          </div>
        </div>
        {!s.embeddingApiBaseUrl.trim() && s.embeddingApiBaseSource !== "env" ? (
          <p className="mt-4 text-xs text-amber-300/90">{t("admin:ifMemNoBaseUrl")}</p>
        ) : null}
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:memoryRagTitle")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemMemoryRagIntro")}</p>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.exposeInternalErrors}
            onChange={(e) => s.setExposeInternalErrors(e.target.checked)}
          />
          {t("admin:ifMemExposeErrors")}
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memoryEnabled}
            onChange={(e) => s.setMemoryEnabled(e.target.checked)}
          />
          {t("admin:ifMemEnableMemory")}
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.ragEnabled}
            onChange={(e) => s.setRagEnabled(e.target.checked)}
          />
          {t("admin:ifMemEnableRag")}
        </label>
        <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="rag-chunk">
              {t("admin:ifMemChunkSize")}
            </label>
            <input
              id="rag-chunk"
              type="number"
              min={200}
              max={8000}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.ragChunkSize}
              onChange={(e) => s.setRagChunkSize(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="rag-overlap">
              {t("admin:ifMemChunkOverlap")}
            </label>
            <input
              id="rag-overlap"
              type="number"
              min={0}
              max={2000}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.ragChunkOverlap}
              onChange={(e) => s.setRagChunkOverlap(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="rag-topk">
              {t("admin:ifMemTopK")}
            </label>
            <input
              id="rag-topk"
              type="number"
              min={1}
              max={50}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.ragTopK}
              onChange={(e) => s.setRagTopK(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="rag-timeout">
              {t("admin:ifMemEmbedTimeout")}
            </label>
            <input
              id="rag-timeout"
              type="number"
              min={5}
              max={600}
              step="1"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.ragEmbedTimeout}
              onChange={(e) => s.setRagEmbedTimeout(e.target.value)}
            />
          </div>
        </div>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="rag-domains">
          {t("admin:ifMemTenantDomains")}
        </label>
        <input
          id="rag-domains"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.ragTenantDomains}
          onChange={(e) => s.setRagTenantDomains(e.target.value)}
          placeholder={t("admin:ifMemoryCollectionPlaceholder")}
        />
        {s.ragTenantEffective.length > 0 ? (
          <p className="mt-2 text-xs text-surface-muted">
            {t("admin:ifMemEffectiveDomains")}{" "}
            <span className="font-mono text-neutral-300">{s.ragTenantEffective.join(", ")}</span>
          </p>
        ) : null}
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="docs-root">
          {t("admin:ifMemDocsPathOptional")}
        </label>
        <input
          id="docs-root"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.docsRoot}
          onChange={(e) => s.setDocsRoot(e.target.value)}
          placeholder={t("admin:ifMemoryDocsPathPlaceholder")}
          autoComplete="off"
        />
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:ifMemGraphTitle")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemGraphIntro")}</p>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memGraphEnabled}
            onChange={(e) => s.setMemGraphEnabled(e.target.checked)}
          />
          {t("admin:ifMemGraphEnable")}
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memGraphLogActivations}
            onChange={(e) => s.setMemGraphLogActivations(e.target.checked)}
          />
          {t("admin:ifMemGraphLog")}
        </label>
        <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="mg-hops">
              {t("admin:ifMemGraphMaxHops")}
            </label>
            <input
              id="mg-hops"
              type="number"
              min={0}
              max={4}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.memGraphMaxHops}
              onChange={(e) => s.setMemGraphMaxHops(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="mg-score">
              {t("admin:ifMemGraphMinScore")}
            </label>
            <input
              id="mg-score"
              type="number"
              step="0.01"
              min={0}
              max={1}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.memGraphMinScore}
              onChange={(e) => s.setMemGraphMinScore(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="mg-bullets">
              {t("admin:ifMemGraphMaxBullets")}
            </label>
            <input
              id="mg-bullets"
              type="number"
              min={1}
              max={50}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.memGraphMaxBullets}
              onChange={(e) => s.setMemGraphMaxBullets(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="mg-chars">
              {t("admin:ifMemGraphMaxChars")}
            </label>
            <input
              id="mg-chars"
              type="number"
              min={200}
              max={50000}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.memGraphMaxPromptChars}
              onChange={(e) => s.setMemGraphMaxPromptChars(e.target.value)}
            />
          </div>
        </div>
      </section>
    </>
  );
}
