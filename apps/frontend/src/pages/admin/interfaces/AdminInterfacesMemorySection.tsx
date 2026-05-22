import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesMemorySection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }
  return (
    <>
          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Memory (Fakten &amp; Notizen) &amp; RAG</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Alles in <span className="font-mono text-neutral-400">operator_settings</span> — keine{" "}
              <span className="font-mono text-neutral-400">AGENT_MEMORY_*</span> /{" "}
              <span className="font-mono text-neutral-400">AGENT_RAG_*</span> mehr. Tool-Pakete weiter unter{" "}
              <span className="text-white/85">Admin → Tools</span>.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.exposeInternalErrors}
                onChange={(e) => s.setExposeInternalErrors(e.target.checked)}
              />
              Interne Fehlertexte in API-Antworten (5xx/502) — nur zum Debuggen; in Produktion aus lassen
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
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="rag-model">
              Embedding-Modell (RAG, von EMBEDDING_BASE_URL /v1/models)
            </label>
            {s.ragEmbeddingModelOptions.length > 0 ? (
              <select
                id="rag-model"
                className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                value={s.ragEmbeddingModel}
                onChange={(e) => s.setRagEmbeddingModel(e.target.value)}
              >
                {s.ragEmbeddingModelOptions.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="rag-model"
                className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                value={s.ragEmbeddingModel}
                onChange={(e) => s.setRagEmbeddingModel(e.target.value)}
                placeholder="nomic-embed-text"
                autoComplete="off"
              />
            )}
            <p className="mt-1 text-xs text-surface-muted">
              API-Host nur in <span className="font-mono">.env</span> (EMBEDDING_BASE_URL). Liste kommt von GET /v1/models
              am Embedding-Server. Beim Speichern übernimmt der Server die passende{" "}
              <span className="font-mono">Embedding-Dim</span> automatisch vom gewählten Modell (z. B. bge-m3 → 1024).
            </p>
            <div className="mt-4 grid max-w-2xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
              Tenant-weite Domains (kommagetrennt). Leer = keine tenant-weiten Domains; Standard oft{" "}
              <span className="font-mono text-neutral-300">agentlayer_docs</span>.
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
                Wirksam geparst:{" "}
                <span className="font-mono text-neutral-300">{s.ragTenantEffective.join(", ")}</span>
              </p>
            ) : null}
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="docs-root">
              Docs-Pfad für <span className="font-mono text-neutral-400">ingest-docs</span> (optional, leer ={" "}
              <span className="font-mono text-neutral-300">…/docs</span> im Image)
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

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Memory graph</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Strukturierte Knoten/Kanten + Prompt-Injection. Gespeichert in der Datenbank (
              <span className="font-mono text-neutral-400">operator_settings</span>
              ). Benötigt aktiviertes Memory oben. Tool-Paket weiter unter{" "}
              <span className="text-white/85">Admin → Tools</span>.
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
