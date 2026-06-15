/** Display helpers for benchmark provider + model (avoids duplicate model in UI). */

const LABEL_MODEL_SEP = " · ";

export type BenchmarkProviderModelFields = {
  profile_label?: string;
  catalog_owned_by?: string;
  model?: string;
};

/** Provider display name — strips composite ``label · model`` suffix when present. */
export function benchmarkProviderName(fields: BenchmarkProviderModelFields): string {
  const model = (fields.model || "").trim();
  const label = (fields.profile_label || "").trim();
  if (label && model && label.endsWith(`${LABEL_MODEL_SEP}${model}`)) {
    return label.slice(0, -(model.length + LABEL_MODEL_SEP.length)).trim();
  }
  return label || (fields.catalog_owned_by || "").trim();
}

/** User-facing ``Provider / model`` (single model, no duplication). */
export function formatBenchmarkProviderModel(fields: BenchmarkProviderModelFields): string {
  const model = (fields.model || "").trim();
  const provider = benchmarkProviderName(fields);
  if (provider && model) return `${provider} / ${model}`;
  return provider || model || "—";
}

/** Internal profile label stored on runs (unique per provider+model). */
export function benchmarkProfileLabel(providerLabel: string, model: string): string {
  const base = providerLabel.trim();
  const m = model.trim();
  if (!base) return m;
  if (!m) return base;
  if (base.endsWith(`${LABEL_MODEL_SEP}${m}`)) return base;
  return `${base}${LABEL_MODEL_SEP}${m}`;
}
