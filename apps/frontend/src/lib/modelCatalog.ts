/**
 * GET /v1/models — merged rows; ``owned_by`` is the opaque provider id (any ``[a-z0-9_-]+`` from the API).
 * Chat must send the same token as ``agent_model_catalog_owned_by`` (no cross-provider fallback).
 */

import i18n from "../i18n/config";
import type { AuthContextValue } from "../auth/AuthContext";
import { apiFetch } from "./api";

export type ProviderHealth = {
  reachable?: boolean;
  configured?: boolean;
  detail?: string | null;
  label?: string | null;
  auth_hint?: string | null;
  base_url?: string;
  endpoint_id?: number;
};

export type EmbeddingCatalogHealth = {
  configured?: boolean;
  reachable?: boolean;
  detail?: string | null;
  model?: string | null;
  embedding_dim?: number;
  actual_embedding_dim?: number;
  dim_matches_config?: boolean;
  dim_mismatch?: boolean;
  embeddings_url?: string | null;
  models_url?: string | null;
  available_models?: string[];
  models_list_detail?: string | null;
  note?: string | null;
};

/** Keys are provider ids (``owned_by``) + optional ``embedding`` (RAG only). */
export type ModelCatalogAgentlayer = Record<string, ProviderHealth | EmbeddingCatalogHealth | undefined> & {
  embedding?: EmbeddingCatalogHealth;
};

export type ModelCapabilities = {
  input_modalities?: string[];
  output_modalities?: string[];
};

export type ModelCapabilityBadge = {
  key: string;
  label: string;
  tone: "text" | "vision" | "audio" | "context";
};

export type ModelRow = {
  id: string;
  owned_by?: string;
  context_length?: number;
  capabilities?: ModelCapabilities;
};

const ROUTING_TOKEN_MAX = 64;

export function normalizeCatalogRoutingToken(raw: string): string | undefined {
  const t = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "")
    .slice(0, ROUTING_TOKEN_MAX);
  return t || undefined;
}

export function providerDisplayLabel(
  ownedBy: string | undefined,
  agentlayer: ModelCatalogAgentlayer | null
): string {
  const key = normalizeCatalogRoutingToken(ownedBy ?? "");
  if (!key) return "unknown";
  const label = agentlayer?.[key]?.label?.trim();
  if (label) return label;
  const adminMatch = /^provider_(\d+)$/.exec(key);
  if (adminMatch && Number(adminMatch[1]) > 32) {
    return `Admin provider ${Number(adminMatch[1]) - 32}`;
  }
  return key.replace(/_/g, " ");
}

export function isProviderCatalogUnreachable(
  providerId: string,
  agentlayer: ModelCatalogAgentlayer | null
): boolean {
  if (!agentlayer) return false;
  const key = normalizeCatalogRoutingToken(providerId);
  if (!key) return false;
  const meta = agentlayer[key];
  if (!meta) return false;
  return meta.reachable === false;
}

export function isCatalogModelOptionDisabled(row: ModelRow, agentlayer: ModelCatalogAgentlayer | null): boolean {
  const key = normalizeCatalogRoutingToken(row.owned_by ?? "");
  if (!key) return false;
  return isProviderCatalogUnreachable(key, agentlayer);
}

export function catalogModelOptionUnreachableTitle(
  row: ModelRow,
  agentlayer: ModelCatalogAgentlayer | null
): string {
  const key = normalizeCatalogRoutingToken(row.owned_by ?? "");
  const label = providerDisplayLabel(row.owned_by, agentlayer);
  const detail = key && agentlayer?.[key]?.detail ? String(agentlayer[key].detail).trim() : "";
  const auth = key && agentlayer?.[key]?.auth_hint ? String(agentlayer[key].auth_hint).trim() : "";
  const base = detail ? `${label} unreachable (${detail})` : `${label} unreachable`;
  if (auth && key && isProviderCatalogUnreachable(key, agentlayer)) {
    return `${base}. ${auth}`;
  }
  return base;
}

export async function fetchModelCatalog(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<{
  rows: ModelRow[];
  agentlayer: ModelCatalogAgentlayer | null;
}> {
  try {
    const r = await apiFetch("/v1/models", auth);
    const raw = (await r.json().catch(() => ({}))) as {
      data?: unknown;
      agentlayer?: ModelCatalogAgentlayer;
    };
    if (!r.ok) {
      return { rows: [], agentlayer: null };
    }
    const data = Array.isArray(raw.data) ? raw.data : [];
    const rows: ModelRow[] = [];
    for (const x of data) {
      if (!x || typeof x !== "object") continue;
      const id = (x as { id?: unknown }).id;
      if (typeof id !== "string" || !id.trim()) continue;
      const ob = (x as { owned_by?: unknown }).owned_by;
      const ctx = (x as { context_length?: unknown }).context_length;
      const caps = (x as { capabilities?: unknown }).capabilities;
      const row: ModelRow = {
        id: id.trim(),
        owned_by: typeof ob === "string" ? ob : undefined,
      };
      if (typeof ctx === "number" && Number.isFinite(ctx) && ctx > 0) {
        row.context_length = Math.floor(ctx);
      }
      if (caps && typeof caps === "object") {
        const c = caps as { input_modalities?: unknown; output_modalities?: unknown };
        row.capabilities = {
          input_modalities: stringArray(c.input_modalities),
          output_modalities: stringArray(c.output_modalities),
        };
      }
      rows.push(row);
    }
    return { rows, agentlayer: raw.agentlayer ?? null };
  } catch {
    return { rows: [], agentlayer: null };
  }
}

function stringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out = value
    .map((x) => (typeof x === "string" ? x.trim().toLowerCase() : ""))
    .filter(Boolean);
  return out.length ? [...new Set(out)] : undefined;
}

export function formatModelCatalogHint(
  agentlayer: ModelCatalogAgentlayer | null,
  opts?: { excludeUnreachableProviderHints?: boolean }
): string | null {
  if (!agentlayer) {
    return "Could not load model catalog (network or server error).";
  }
  const ex = opts?.excludeUnreachableProviderHints === true;
  const msgs: string[] = [];
  for (const [providerId, meta] of Object.entries(agentlayer)) {
    if (providerId === "embedding") continue;
    if (!meta || meta.reachable !== false) continue;
    if (ex && isProviderCatalogUnreachable(providerId, agentlayer)) continue;
    const detail = (meta.detail ?? "").trim();
    const label = providerDisplayLabel(providerId, agentlayer);
    if (detail && detail !== "not_configured") {
      msgs.push(`${label}: ${detail}`);
    } else {
      msgs.push(`${label} unreachable`);
    }
    const auth = (meta.auth_hint ?? "").trim();
    if (auth) msgs.push(auth);
  }
  if (msgs.length === 0) return null;
  return msgs.join(" · ");
}

/** Shown when GET /v1/models returns no rows (chat providers down or misconfigured). */
export function formatEmptyChatModelCatalogHint(
  agentlayer: ModelCatalogAgentlayer | null
): string | null {
  const chat = formatModelCatalogHint(agentlayer, { excludeUnreachableProviderHints: false });
  if (chat) return `Chat models unavailable — ${chat}`;
  return "No chat models in catalog. Check LLM_PROVIDER_1_* in .env or Admin → LLM-Endpoints.";
}

export function modelOptionLabel(row: ModelRow, agentlayer?: ModelCatalogAgentlayer | null): string {
  const ob = row.owned_by?.trim();
  const badges = modelCapabilityBadges(row).map((b) => b.label);
  const badgeSuffix = badges.length ? ` · ${badges.join(" · ")}` : "";
  if (!ob) return `${row.id}${badgeSuffix}`;
  const label = providerDisplayLabel(ob, agentlayer ?? null);
  return `${row.id} (${label})${badgeSuffix}`;
}

export function formatContextLengthBadge(contextLength: number | undefined): string | null {
  if (!contextLength || !Number.isFinite(contextLength) || contextLength <= 0) return null;
  if (contextLength >= 1000) {
    const k = contextLength / 1000;
    const rounded = k >= 100 ? Math.round(k) : Math.round(k * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}k`;
  }
  return `${Math.floor(contextLength)}`;
}

export function modelCapabilityBadges(row: ModelRow): ModelCapabilityBadge[] {
  const input = new Set(row.capabilities?.input_modalities ?? []);
  const output = new Set(row.capabilities?.output_modalities ?? []);
  const hasAnyModalities = input.size > 0 || output.size > 0;
  const badges: ModelCapabilityBadge[] = [];

  if (!hasAnyModalities || input.has("text") || output.has("text")) {
    badges.push({ key: "text", label: "Text", tone: "text" });
  }
  if (input.has("image") || output.has("image") || input.has("vision") || output.has("vision")) {
    badges.push({ key: "vision", label: "Vision", tone: "vision" });
  }
  if (input.has("audio") || output.has("audio")) {
    badges.push({ key: "audio", label: "Audio", tone: "audio" });
  }

  const ctx = formatContextLengthBadge(row.context_length);
  if (ctx) badges.push({ key: "context", label: ctx, tone: "context" });
  return badges;
}

/** Chat model ids for one catalog provider (``owned_by`` / ``catalog_owned_by``). */
export function catalogModelIdsForProvider(rows: ModelRow[], catalogOwnedBy: string): string[] {
  const key = normalizeCatalogRoutingToken(catalogOwnedBy);
  if (!key) return [];
  const ids = rows
    .filter((r) => normalizeCatalogRoutingToken(r.owned_by ?? "") === key)
    .map((r) => r.id.trim())
    .filter(Boolean);
  return [...new Set(ids)].sort((a, b) => a.localeCompare(b));
}

/** Short id for compact UI (sidebar, session bar) — no provider suffix. */
export function compactModelDisplayName(modelId: string, maxLen = 26): string {
  const raw = (modelId || "").trim();
  if (!raw) return "";
  const base = raw.replace(/\.gguf$/i, "").split("/").pop() || raw;
  if (base.length <= maxLen) return base;
  return `${base.slice(0, Math.max(8, maxLen - 1))}…`;
}

export function modelCatalogSelectValue(row: ModelRow): string {
  const ob = normalizeCatalogRoutingToken(row.owned_by ?? "") ?? "unknown";
  return `${ob}:${row.id}`;
}

export type ModelCatalogSelection = { modelId: string; provider?: string };

export function parseModelCatalogSelection(raw: string): ModelCatalogSelection {
  const s = (raw || "").trim();
  const colon = s.indexOf(":");
  if (colon > 0) {
    const provider = normalizeCatalogRoutingToken(s.slice(0, colon));
    const modelId = s.slice(colon + 1).trim();
    if (modelId) return { modelId, provider };
  }
  return { modelId: s };
}

function normalizeModelIdKey(id: string): string {
  return id.trim().toLowerCase().replace(/\.gguf$/i, "");
}

/** Match catalog row when thread stores a shortened or differently-cased model id. */
export function findCatalogRowByModelId(
  rows: ModelRow[],
  modelId: string,
  preferredProvider?: string
): ModelRow | undefined {
  const id = modelId.trim();
  if (!id) return undefined;
  const pref = normalizeCatalogRoutingToken(preferredProvider ?? "");
  const exact = rows.filter((r) => r.id === id);
  if (exact.length === 1) return exact[0];
  if (exact.length > 1 && pref) {
    const hit = exact.find((r) => normalizeCatalogRoutingToken(r.owned_by ?? "") === pref);
    if (hit) return hit;
  }
  const key = normalizeModelIdKey(id);
  const loose = rows.filter((r) => normalizeModelIdKey(r.id) === key);
  if (loose.length === 1) return loose[0];
  if (loose.length > 1 && pref) {
    const hit = loose.find((r) => normalizeCatalogRoutingToken(r.owned_by ?? "") === pref);
    if (hit) return hit;
  }
  return undefined;
}

export function catalogRowForSelection(rows: ModelRow[], selection: string): ModelRow | undefined {
  const { modelId, provider } = parseModelCatalogSelection(selection);
  if (!modelId) return undefined;
  if (provider) {
    const hit = rows.find(
      (r) => r.id === modelId && normalizeCatalogRoutingToken(r.owned_by ?? "") === provider
    );
    if (hit) return hit;
    const key = normalizeModelIdKey(modelId);
    const loose = rows.filter(
      (r) =>
        normalizeModelIdKey(r.id) === key &&
        normalizeCatalogRoutingToken(r.owned_by ?? "") === provider
    );
    if (loose.length === 1) return loose[0];
    return undefined;
  }
  const matches = rows.filter((r) => r.id === modelId);
  if (matches.length === 1) return matches[0];
  return findCatalogRowByModelId(rows, modelId);
}

export function catalogProviderForModel(rows: ModelRow[], modelIdOrSelection: string): string | undefined {
  const row = catalogRowForSelection(rows, modelIdOrSelection);
  if (row?.owned_by) return normalizeCatalogRoutingToken(row.owned_by);
  return parseModelCatalogSelection(modelIdOrSelection).provider;
}

export function modelCatalogSelectValueForThread(modelId: string, modelProvider?: string): string {
  const id = modelId.trim();
  if (!id) return "";
  const ob = normalizeCatalogRoutingToken(modelProvider ?? "");
  return ob ? `${ob}:${id}` : id;
}

export function applyModelCatalogSelection(
  raw: string,
  rows: ModelRow[]
): { model: string; modelProvider?: string } {
  const row = catalogRowForSelection(rows, raw);
  const parsed = parseModelCatalogSelection(raw);
  const model = (row?.id ?? parsed.modelId).trim();
  const modelProvider =
    parsed.provider ??
    (row?.owned_by ? normalizeCatalogRoutingToken(row.owned_by) : undefined);
  return { model, modelProvider };
}

/**
 * Resolve chat routing from the **current** model dropdown value (wins over stale thread fields).
 */
export function resolveComposerModelRouting(
  rows: ModelRow[],
  selectValue: string,
  threadModel?: string,
  threadProvider?: string
): { model: string; provider: string } | null {
  const sel = parseModelCatalogSelection((selectValue || "").trim());
  const modelId = (sel.modelId || (threadModel ?? "").trim()).trim();
  const provider = sel.provider || threadProvider;
  return resolveModelCatalogRouting(rows, modelId, provider, selectValue);
}

/**
 * Dropdown / composer value aligned with ``<select value=…>`` (``provider:model`` when catalog allows).
 */
export function composerSelectValueForThread(
  rows: ModelRow[],
  modelId: string,
  modelProvider?: string,
  defaultSelectValue?: string
): string {
  const id = modelId.trim();
  const fromThread = modelCatalogSelectValueForThread(id, modelProvider);
  if (fromThread.includes(":")) return fromThread;
  const row = findCatalogRowByModelId(rows, id, modelProvider);
  if (row?.owned_by) return modelCatalogSelectValue(row);
  const def = (defaultSelectValue ?? "").trim();
  if (id && def.includes(":")) {
    const parsed = parseModelCatalogSelection(def);
    if (
      parsed.modelId &&
      normalizeModelIdKey(parsed.modelId) === normalizeModelIdKey(id)
    ) {
      return def;
    }
  }
  if (id) return fromThread;
  return def;
}

/**
 * Resolve provider + model for send — matches visible dropdown (incl. ``defaultSelectValue`` fallback).
 */
export function resolveSendModelRouting(
  rows: ModelRow[],
  opts: {
    lastSelection?: string;
    modelSelectValue: string;
    defaultSelectValue: string;
    threadModel?: string;
    threadProvider?: string;
  }
): { model: string; provider: string; selectValue: string } | null {
  const effectiveSelect = composerSelectValueForThread(
    rows,
    (opts.threadModel ?? "").trim(),
    opts.threadProvider,
    opts.defaultSelectValue
  );
  const candidates = [
    opts.lastSelection,
    opts.modelSelectValue,
    effectiveSelect,
    opts.defaultSelectValue,
  ];
  const seen = new Set<string>();
  for (const raw of candidates) {
    const sel = (raw ?? "").trim();
    if (!sel || seen.has(sel)) continue;
    seen.add(sel);
    const routed = resolveComposerModelRouting(
      rows,
      sel,
      opts.threadModel,
      opts.threadProvider
    );
    if (routed) return { ...routed, selectValue: sel };
  }
  return null;
}

/**
 * Resolve provider + canonical model id for chat.
 * Uses stored provider, dropdown composite value, then catalog row lookup (incl. case / .gguf).
 */
/** Chat routing: only explicit dropdown value (``provider:model``) or stored ``modelProvider`` — no guessing. */
export function resolveModelCatalogRouting(
  rows: ModelRow[],
  modelId: string,
  modelProvider?: string,
  selectValueHint?: string
): { model: string; provider: string } | null {
  const hint = (selectValueHint ?? "").trim();
  if (hint.includes(":")) {
    const parsed = parseModelCatalogSelection(hint);
    const prov = normalizeCatalogRoutingToken(parsed.provider ?? "");
    if (prov && parsed.modelId) {
      const row = catalogRowForSelection(rows, hint);
      return { model: (row?.id ?? parsed.modelId).trim(), provider: prov };
    }
  }
  const stored = normalizeCatalogRoutingToken(modelProvider ?? "");
  if (stored && modelId.trim()) {
    const row = catalogRowForSelection(
      rows,
      modelCatalogSelectValueForThread(modelId, stored)
    );
    return { model: (row?.id ?? modelId).trim(), provider: stored };
  }
  const row = findCatalogRowByModelId(rows, modelId.trim(), modelProvider);
  if (row?.owned_by) {
    const prov = normalizeCatalogRoutingToken(row.owned_by);
    if (prov) return { model: row.id, provider: prov };
  }
  return null;
}

export function embeddingModelOptions(emb: EmbeddingCatalogHealth | null | undefined): string[] {
  if (!emb) return [];
  const fromApi = Array.isArray(emb.available_models)
    ? emb.available_models.map((m) => String(m).trim()).filter(Boolean)
    : [];
  const current = (emb.model ?? "").trim();
  if (current && !fromApi.includes(current)) {
    return [current, ...fromApi];
  }
  return fromApi.length > 0 ? fromApi : current ? [current] : [];
}

/** Short status under the RAG model dropdown (not a replacement for it). */
export function formatEmbeddingStatusHint(emb: EmbeddingCatalogHealth | null | undefined): string | null {
  if (!emb?.configured) {
    return i18n.t("errors:embeddingNotConfigured");
  }
  if (emb.dim_mismatch || emb.dim_matches_config === false) {
    const actual = emb.actual_embedding_dim;
    const cfg = emb.embedding_dim;
    if (actual != null && cfg != null) {
      return i18n.t("errors:embeddingDimMismatch", { actual, cfg });
    }
  }
  if (emb.reachable === true && emb.dim_matches_config !== false) {
    return i18n.t("errors:embeddingApiReachable");
  }
  const detail = (emb.detail ?? "").trim();
  if (detail.includes("501") || detail.toLowerCase().includes("not implemented")) {
    return i18n.t("errors:embeddingNoV1Endpoint");
  }
  if (detail) return i18n.t("errors:embeddingDetail", { detail });
  const listErr = (emb.models_list_detail ?? "").trim();
  if (listErr) return i18n.t("errors:embeddingModelListDetail", { detail: listErr });
  return null;
}

export async function patchEmbeddingModel(
  auth: { accessToken: string | null },
  modelId: string,
  opts?: { embeddingDim?: number }
): Promise<{ ok: boolean; embeddingDim?: number }> {
  const id = modelId.trim();
  if (!id) return { ok: false };
  const body: Record<string, unknown> = { rag_embedding_model: id };
  const dim = opts?.embeddingDim;
  if (typeof dim === "number" && Number.isFinite(dim) && dim >= 32 && dim <= 4096) {
    body.rag_embedding_dim = Math.floor(dim);
  }
  const { apiFetch } = await import("./api");
  const r = await apiFetch("/v1/admin/operator-settings", auth, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return { ok: false };
  try {
    const data = (await r.json()) as { rag_embedding_dim?: number };
    const saved =
      data.rag_embedding_dim != null && Number.isFinite(data.rag_embedding_dim)
        ? data.rag_embedding_dim
        : undefined;
    return { ok: true, embeddingDim: saved };
  } catch {
    return { ok: true };
  }
}

export function defaultModelCatalogSelectValue(rows: ModelRow[]): string {
  return rows[0] ? modelCatalogSelectValue(rows[0]) : "";
}

/** @deprecated use resolveModelCatalogRouting */
export function requireModelProvider(
  rows: ModelRow[],
  modelId: string,
  modelProvider?: string,
  selectValueHint?: string
): string | undefined {
  return resolveModelCatalogRouting(rows, modelId, modelProvider, selectValueHint)?.provider;
}
