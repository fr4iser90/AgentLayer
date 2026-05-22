import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesMemorySection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }

  const embedModelsOk = s.ragEmbeddingModelOptions.length > 0;

  return (
    <>
      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">Embedding-Endpoints (RAG &amp; Memory)</h2>
        <p className="mt-2 text-xs text-surface-muted">
          Getrennt vom Chat unter{" "}
          <span className="text-sky-400/90">Interfaces → LLM &amp; routing</span>. OpenAI-kompatibel:{" "}
          <span className="font-mono">POST …/v1/embeddings</span>. Base URL hier in der DB oder via{" "}
          <span className="font-mono">EMBEDDING_BASE_URL</span> in <span className="font-mono">.env</span> (Env
          überschreibt DB). Key und Header-Name unten speichern (wie LLM-Endpoints) oder via{" "}
          <span className="font-mono">EMBEDDING_API_HEADER_*</span> in <span className="font-mono">.env</span>.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
            disabled={s.embeddingModelsLoading}
            onClick={() => void s.refreshEmbeddingCatalog()}
          >
            {s.embeddingModelsLoading ? "Lade Modelle…" : "Modelle laden (Embedding-API)"}
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
              <span className="text-xs font-medium text-surface-muted">Endpoint 1</span>
              {s.embeddingApiBaseSource === "env" ? (
                <span className="text-xs text-amber-300/90">Base URL aus .env</span>
              ) : s.embeddingApiBaseEffective ? (
                <span className="font-mono text-xs text-neutral-500">aktiv</span>
              ) : null}
            </div>
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="embedding-base-url">
              Base URL
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
              placeholder="https://embed-llm.example.com/v1"
              autoComplete="off"
              disabled={s.embeddingApiBaseSource === "env"}
            />
            {s.embeddingApiBaseSource === "env" ? (
              <p className="mt-1 text-xs text-surface-muted">
                <span className="font-mono">EMBEDDING_BASE_URL</span> in <span className="font-mono">.env</span>{" "}
                überschreibt die DB. Feld leer lassen in <span className="font-mono">.env</span>, um die URL unten zu
                speichern.
              </p>
            ) : s.embeddingApiBaseEffective ? (
              <p className="mt-1 text-xs text-surface-muted">
                Wirksam nach Save:{" "}
                <span className="font-mono text-neutral-300">{s.embeddingApiBaseEffective}</span>
              </p>
            ) : null}
            <p className="mt-3 text-xs text-surface-muted">
              Key: {s.embeddingApiKeyConfigured ? "gespeichert" : "—"}
              {s.embeddingApiKeySource === "env" ? (
                <span className="text-amber-300/90"> (aus .env)</span>
              ) : null}
            </p>
            <label className="mt-2 block text-xs text-surface-muted" htmlFor="embedding-api-key">
              API-Key (leer lassen = gespeicherten Key behalten)
            </label>
            <input
              id="embedding-api-key"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
              value={s.embeddingApiKey}
              onChange={(e) => s.setEmbeddingApiKey(e.target.value)}
              placeholder={s.embeddingApiKeyConfigured ? "•••• (neu = ersetzen)" : "Key einfügen"}
              disabled={s.embeddingApiKeySource === "env"}
            />
            {s.embeddingApiKeySource === "env" ? (
              <p className="mt-1 text-xs text-surface-muted">
                <span className="font-mono">EMBEDDING_API_HEADER_VALUE</span> in <span className="font-mono">.env</span>{" "}
                überschreibt den DB-Key.
              </p>
            ) : null}
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="embedding-header-name">
              Header-Name für den Key
            </label>
            <input
              id="embedding-header-name"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-50"
              value={s.embeddingApiHeaderName}
              onChange={(e) => s.setEmbeddingApiHeaderName(e.target.value)}
              placeholder="X-API-KEY"
              autoComplete="off"
              disabled={s.embeddingApiKeySource === "env"}
            />
            <p className="mt-1 text-xs text-surface-muted">
              Wirksam: <span className="font-mono text-neutral-300">{s.embeddingApiHeaderNameEffective}</span>
              {s.embeddingApiHeaderNameSource === "env" ? " (aus .env)" : ""}.{" "}
              <span className="font-mono">Authorization</span> → Bearer automatisch.
            </p>
            <h4 className="mt-4 text-xs font-medium uppercase tracking-wide text-surface-muted">
              Embedding-Modell
            </h4>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-model">
                  Modell-ID
                </label>
                <input
                  id="rag-model"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.ragEmbeddingModel}
                  onChange={(e) => s.setRagEmbeddingModel(e.target.value)}
                  placeholder="bge-m3-Q4_K_M.gguf"
                  list="embed-model-ids"
                  autoComplete="off"
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="rag-dim">
                  Embedding-Dim (32–4096)
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
            <p className="mt-2 text-xs text-surface-muted">
              Nach <span className="text-white/80">Save</span> synchronisiert der Server Modell/Dim mit dem Provider.
            </p>
          </div>
        </div>
        {!s.embeddingApiBaseUrl.trim() && s.embeddingApiBaseSource !== "env" ? (
          <p className="mt-4 text-xs text-amber-300/90">
            Noch keine Base URL — <span className="font-mono">EMBEDDING_BASE_URL</span> in{" "}
            <span className="font-mono">.env</span> oder URL eintragen und speichern.
          </p>
        ) : null}
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">Memory &amp; RAG</h2>
        <p className="mt-2 text-xs text-surface-muted">
          Schalter und Tuning in <span className="font-mono text-neutral-400">operator_settings</span>. Tool-Pakete unter{" "}
          <span className="text-white/85">Admin → Tools</span>.
        </p>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.exposeInternalErrors}
            onChange={(e) => s.setExposeInternalErrors(e.target.checked)}
          />
          Interne Fehlertexte in API-Antworten (5xx/502) — nur zum Debuggen
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memoryEnabled}
            onChange={(e) => s.setMemoryEnabled(e.target.checked)}
          />
          Memory (Fakten, semantische Notizen, APIs) aktivieren
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.ragEnabled}
            onChange={(e) => s.setRagEnabled(e.target.checked)}
          />
          RAG (pgvector-Ingest &amp; Suche) aktivieren
        </label>
        <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="rag-chunk">
              Chunk-Größe (200–8000)
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
              Chunk-Overlap (0–2000)
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
              Top-K (1–50)
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
              Embed-Timeout (Sek., 5–600)
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
          Tenant-weite Domains (kommagetrennt)
        </label>
        <input
          id="rag-domains"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.ragTenantDomains}
          onChange={(e) => s.setRagTenantDomains(e.target.value)}
          placeholder="agentlayer_docs"
        />
        {s.ragTenantEffective.length > 0 ? (
          <p className="mt-2 text-xs text-surface-muted">
            Wirksam: <span className="font-mono text-neutral-300">{s.ragTenantEffective.join(", ")}</span>
          </p>
        ) : null}
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="docs-root">
          Docs-Pfad für <span className="font-mono text-neutral-400">ingest-docs</span> (optional)
        </label>
        <input
          id="docs-root"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.docsRoot}
          onChange={(e) => s.setDocsRoot(e.target.value)}
          placeholder="/pfad/zum/docs"
          autoComplete="off"
        />
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">Memory graph</h2>
        <p className="mt-2 text-xs text-surface-muted">
          Strukturierte Knoten/Kanten + Prompt-Injection. Benötigt aktiviertes Memory oben.
        </p>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memGraphEnabled}
            onChange={(e) => s.setMemGraphEnabled(e.target.checked)}
          />
          Graph-Speicherung und Kontext-Injection aktivieren
        </label>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.memGraphLogActivations}
            onChange={(e) => s.setMemGraphLogActivations(e.target.checked)}
          />
          Aktivierungs-Log schreiben (node ids, gehashte Query — kein Rohtext)
        </label>
        <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs text-surface-muted" htmlFor="mg-hops">
              Max. Hops (0–4)
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
              Min. Aktivierungsscore (0–1)
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
              Max. Bullet-Zeilen
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
              Max. Zeichen (Graph-Block)
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
