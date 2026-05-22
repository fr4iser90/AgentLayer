import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesLlmSection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }
  return (
    <>
          <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">LLM-Endpoints (Chat-Provider)</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Jeder Eintrag = ein Provider im Chat-Model-Dropdown (<span className="font-mono">external_1</span>,{" "}
              <span className="font-mono">external_2</span>, …). URL + Key eintragen, speichern, dann im Chat Provider
              und Modell wählen (<span className="font-mono">agent_model_catalog_owned_by</span>). OpenAI-kompatibel:
              OpenAI, Groq, Gemini, llama.cpp, …               Zusätzlich aus <span className="font-mono">.env</span>:{" "}
              <span className="font-mono">OLLAMA_BASE_URL</span> → <span className="font-mono">ollama</span>,{" "}
              <span className="font-mono">LLAMA_CPP_*</span> → <span className="font-mono">llama_cpp</span>.{" "}
              <span className="text-white/85">Embeddings</span> (RAG/Memory):{" "}
              <span className="text-sky-400/90">Interfaces → Memory &amp; RAG</span>.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20"
                onClick={() =>
                  s.setExtLlmEndpoints((prev) => [
                    ...prev,
                    {
                      localKey: `new-${Date.now()}`,
                      id: null,
                      enabled: true,
                      label: "",
                      baseUrl: "",
                      apiKey: "",
                      apiKeyConfigured: false,
                      modelDefault: "",
                      modelVlm: "",
                      modelAgent: "",
                      modelCoding: "",
                    },
                  ])
                }
              >
                Endpoint hinzufügen
              </button>
              <button
                type="button"
                className="rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
                disabled={s.extLlmModelsLoading}
                onClick={() => void s.loadExternalModels()}
              >
                {s.extLlmModelsLoading ? "Lade Modelle…" : "Modelle laden (erster Endpoint mit URL)"}
              </button>
            </div>
            {s.extLlmModelsHint ? (
              <p
                className={`mt-2 text-xs ${
                  s.extLlmModelIds.length > 0 ? "text-emerald-400/90" : "text-amber-300/90"
                }`}
              >
                {s.extLlmModelsHint}
              </p>
            ) : null}
            <datalist id="ext-llm-model-ids">
              {s.extLlmModelIds.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>

            <div className="mt-6 space-y-6">
              {s.extLlmEndpoints.map((ep, idx) => (
                <div
                  key={ep.localKey}
                  className="rounded-lg border border-white/10 bg-black/15 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium text-surface-muted">
                      Endpoint {idx + 1}
                      {ep.id != null ? (
                        <span className="ml-2 font-mono text-neutral-500">id={ep.id}</span>
                      ) : null}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="text-xs text-neutral-400 hover:text-white"
                        disabled={idx === 0}
                        onClick={() =>
                          s.setExtLlmEndpoints((prev) => {
                            const n = [...prev];
                            [n[idx - 1], n[idx]] = [n[idx], n[idx - 1]];
                            return n;
                          })
                        }
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="text-xs text-neutral-400 hover:text-white"
                        disabled={idx >= s.extLlmEndpoints.length - 1}
                        onClick={() =>
                          s.setExtLlmEndpoints((prev) => {
                            const n = [...prev];
                            [n[idx], n[idx + 1]] = [n[idx + 1], n[idx]];
                            return n;
                          })
                        }
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="text-xs text-rose-400 hover:text-rose-200"
                        onClick={() =>
                          s.setExtLlmEndpoints((prev) => prev.filter((_, j) => j !== idx))
                        }
                      >
                        Entfernen
                      </button>
                    </div>
                  </div>
                  <label className="mt-2 block text-xs text-surface-muted" htmlFor={`ep-lbl-${ep.localKey}`}>
                    Label (optional)
                  </label>
                  <input
                    id={`ep-lbl-${ep.localKey}`}
                    className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
                    value={ep.label}
                    onChange={(e) => {
                      const v = e.target.value;
                      s.setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, label: v } : x))
                      );
                    }}
                    placeholder="z. B. Google, OpenAI Backup"
                  />
                  <label className="mt-3 block text-xs text-surface-muted" htmlFor={`ep-url-${ep.localKey}`}>
                    Base URL
                  </label>
                  <input
                    id={`ep-url-${ep.localKey}`}
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                    value={ep.baseUrl}
                    onChange={(e) => {
                      const v = e.target.value;
                      s.setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, baseUrl: v } : x))
                      );
                    }}
                    placeholder="https://api.openai.com"
                    autoComplete="off"
                  />
                  <p className="mt-1 text-xs text-surface-muted">
                    Key: {ep.apiKeyConfigured ? "gespeichert" : "—"}
                  </p>
                  <label className="mt-2 block text-xs text-surface-muted" htmlFor={`ep-key-${ep.localKey}`}>
                    API-Key (leer lassen = gespeicherten Key behalten)
                  </label>
                  <input
                    id={`ep-key-${ep.localKey}`}
                    type="password"
                    autoComplete="off"
                    className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                    value={ep.apiKey}
                    onChange={(e) => {
                      const v = e.target.value;
                      s.setExtLlmEndpoints((prev) =>
                        prev.map((x, j) => (j === idx ? { ...x, apiKey: v } : x))
                      );
                    }}
                    placeholder={ep.apiKeyConfigured ? "•••• (neu = ersetzen)" : "Key einfügen"}
                  />
                  <h4 className="mt-4 text-xs font-medium uppercase tracking-wide text-surface-muted">
                    Modell-IDs (OpenAI-Namen)
                  </h4>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-md-${ep.localKey}`}>
                        Default
                      </label>
                      <input
                        id={`ep-md-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelDefault}
                        onChange={(e) => {
                          const v = e.target.value;
                          s.setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelDefault: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-mv-${ep.localKey}`}>
                        VLM
                      </label>
                      <input
                        id={`ep-mv-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelVlm}
                        onChange={(e) => {
                          const v = e.target.value;
                          s.setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelVlm: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-ma-${ep.localKey}`}>
                        Agent
                      </label>
                      <input
                        id={`ep-ma-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelAgent}
                        onChange={(e) => {
                          const v = e.target.value;
                          s.setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelAgent: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-surface-muted" htmlFor={`ep-mc-${ep.localKey}`}>
                        Coding
                      </label>
                      <input
                        id={`ep-mc-${ep.localKey}`}
                        className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                        value={ep.modelCoding}
                        onChange={(e) => {
                          const v = e.target.value;
                          s.setExtLlmEndpoints((prev) =>
                            prev.map((x, j) => (j === idx ? { ...x, modelCoding: v } : x))
                          );
                        }}
                        list="ext-llm-model-ids"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {s.extLlmEndpoints.length === 0 ? (
              <p className="mt-4 text-xs text-amber-300/90">
                Noch keine Endpoints — <span className="font-mono">ollama</span> /{" "}
                <span className="font-mono">llama_cpp</span> aus <span className="font-mono">.env</span> oder Endpoint
                hinzufügen.
              </p>
            ) : null}
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Smart LLM-Routing (optional)</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Experimentell: Heuristik + kleines Router-Modell auf <span className="font-mono">OLLAMA_BASE_URL</span>.
              Der Chat nutzt sonst den im Composer gewählten Katalog-Provider — Smart Routing ersetzt diesen Schalter
              nicht. Nur sinnvoll, wenn du parallel lokales Ollama und externe APIs nutzt.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.llmSmartRouting}
                onChange={(e) => s.setLlmSmartRouting(e.target.checked)}
              />
              Smart Routing aktivieren
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="llm-router-model">
              Router-Modell (Ollama, klein, z. B. 3–6B)
            </label>
            <input
              id="llm-router-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.llmRouterModel}
              onChange={(e) => s.setLlmRouterModel(e.target.value)}
              placeholder="nemotron-3-nano:4b"
              autoComplete="off"
            />
            <div className="mt-4 grid max-w-xl gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-router-conf">
                  Min. Konfidenz für „lokal“ (0–1)
                </label>
                <input
                  id="llm-router-conf"
                  type="number"
                  step="0.05"
                  min={0}
                  max={1}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouterConfMin}
                  onChange={(e) => s.setLlmRouterConfMin(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-router-to">
                  Router-Timeout (Sekunden, 1–120)
                </label>
                <input
                  id="llm-router-to"
                  type="number"
                  min={1}
                  max={120}
                  step="1"
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouterTimeoutSec}
                  onChange={(e) => s.setLlmRouterTimeoutSec(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-long">
                  Lange letzte User-Nachricht ab (Zeichen) → eher extern
                </label>
                <input
                  id="llm-route-long"
                  type="number"
                  min={100}
                  max={500000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouteLongChars}
                  onChange={(e) => s.setLlmRouteLongChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-short">
                  Kurze Nachricht bis (Zeichen) → eher lokal
                </label>
                <input
                  id="llm-route-short"
                  type="number"
                  min={1}
                  max={50000}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouteShortChars}
                  onChange={(e) => s.setLlmRouteShortChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-fences">
                  Code-Blöcke (Schwelle, ≥)
                </label>
                <input
                  id="llm-route-fences"
                  type="number"
                  min={1}
                  max={100}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouteManyFences}
                  onChange={(e) => s.setLlmRouteManyFences(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-surface-muted" htmlFor="llm-route-msgs">
                  Viele Turns (über) → eher extern
                </label>
                <input
                  id="llm-route-msgs"
                  type="number"
                  min={1}
                  max={500}
                  className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
                  value={s.llmRouteManyMsgs}
                  onChange={(e) => s.setLlmRouteManyMsgs(e.target.value)}
                />
              </div>
            </div>
          </section>
    </>
  );
}
