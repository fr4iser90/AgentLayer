import { benchmarkProfileLabel } from "./benchDisplayUtils";
import type { BenchmarkLlmProvider, BenchmarkProfileInput } from "./benchmarksApi";

export function defaultProviderModel(p: BenchmarkLlmProvider): string {
  return (p.model_agent || p.model_default || p.model_coding || "").trim();
}

export function normalizeProviderModels(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of raw) {
    const id = String(item ?? "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

export function modelsByProviderFromRecord(
  raw: Record<string, unknown> | undefined
): Map<string, string[]> {
  const out = new Map<string, string[]>();
  if (!raw || typeof raw !== "object") return out;
  for (const [key, val] of Object.entries(raw)) {
    const id = key.trim();
    if (!id) continue;
    const models = normalizeProviderModels(val);
    if (models.length) out.set(id, models);
  }
  return out;
}

export function buildProfilesFromSelection(
  providers: BenchmarkLlmProvider[],
  selectedIds: ReadonlySet<string>,
  modelsByProviderId: ReadonlyMap<string, string[]>
): BenchmarkProfileInput[] {
  const profiles: BenchmarkProfileInput[] = [];
  for (const p of providers) {
    if (!selectedIds.has(p.catalog_owned_by)) continue;
    const models = modelsByProviderId.get(p.catalog_owned_by) ?? [];
    const fallback = defaultProviderModel(p);
    const effective = models.length ? models : fallback ? [fallback] : [];
    for (const model of effective) {
      const trimmed = model.trim();
      if (!trimmed) continue;
      profiles.push({
        catalog_owned_by: p.catalog_owned_by,
        endpoint_id: p.endpoint_id ?? undefined,
        label: benchmarkProfileLabel(p.label || p.catalog_owned_by || "bench", trimmed),
        model: trimmed,
      });
    }
  }
  return profiles;
}

export function countProfilesFromSelection(
  providers: BenchmarkLlmProvider[],
  selectedIds: ReadonlySet<string>,
  modelsByProviderId: ReadonlyMap<string, string[]>
): number {
  return buildProfilesFromSelection(providers, selectedIds, modelsByProviderId).length;
}
