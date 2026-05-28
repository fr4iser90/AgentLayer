import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useTranslation } from "react-i18next";

export function AdminInterfacesMemorySection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">{t("admin:loading")}</p>;
  }

  const embedModelsOk = s.ragEmbeddingModelOptions.length > 0;

  return (
    <>
      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:ifMemEmbedTitle")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifMemEmbedIntro")}</p>
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
                <span className="font-mono">EMBEDDING_BASE_URL</span> {t("admin:ifMemInDotenv")}{" "}
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
                <input
                  id="rag-model"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.ragEmbeddingModel}
                  onChange={(e) => s.setRagEmbeddingModel(e.target.value)}
                  placeholder={t("admin:ifMemoryModelFilePlaceholder")}
                  list="embed-model-ids"
                  autoComplete="off"
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
