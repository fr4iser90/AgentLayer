/**
 * GET /v1/models — merged model rows; ``owned_by`` identifies the serving stack (opaque string from API).
 * Chat sends ``agent_model_catalog_owned_by`` with the same token so the backend can route when ids overlap.
 */

export type ModelCatalogAgentlayer = {
  ollama?: { reachable?: boolean; detail?: string | null; base_url?: string };
  llama_cpp?: {
    configured?: boolean;
    reachable?: boolean;
    detail?: string | null;
    auth_hint?: string | null;
    models_url?: string;
    header_value_configured?: boolean;
    header_name?: string;
    sends_authorization_bearer?: boolean;
  };
};

export type ModelRow = { id: string; owned_by?: string };

const ROUTING_TOKEN_MAX = 64;

/** Safe token for ``agent_model_catalog_owned_by`` (must stay in sync with backend). */
export function normalizeCatalogRoutingToken(raw: string): string | undefined {
  const t = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "")
    .slice(0, ROUTING_TOKEN_MAX);
  return t || undefined;
}

/** ``owned_by`` values we map to ``agentlayer`` health blocks (extend when backend adds more). */
const CATALOG_PROVIDER_KEYS = ["ollama", "llama_cpp"] as const;
type CatalogProviderKey = (typeof CATALOG_PROVIDER_KEYS)[number];

function catalogProviderKey(ownedBy: string | undefined): CatalogProviderKey | null {
  const t = normalizeCatalogRoutingToken(ownedBy ?? "");
  if (!t) return null;
  return (CATALOG_PROVIDER_KEYS as readonly string[]).includes(t) ? (t as CatalogProviderKey) : null;
}

/**
 * True when the catalog says this stack is down / unreachable for rows with this ``owned_by``.
 * Keeps rules aligned with ``formatModelCatalogHint`` for each provider.
 */
export function isProviderCatalogUnreachable(
  provider: CatalogProviderKey,
  agentlayer: ModelCatalogAgentlayer | null
): boolean {
  if (!agentlayer) return false;
  if (provider === "ollama") {
    const o = agentlayer.ollama;
    return o != null && o.reachable === false;
  }
  if (provider === "llama_cpp") {
    const l = agentlayer.llama_cpp;
    return !!(l?.configured && l.reachable === false);
  }
  return false;
}

/** Disable dropdown option: model belongs to a catalog provider that is currently unreachable. */
export function isCatalogModelOptionDisabled(row: ModelRow, agentlayer: ModelCatalogAgentlayer | null): boolean {
  const key = catalogProviderKey(row.owned_by);
  if (!key) return false;
  return isProviderCatalogUnreachable(key, agentlayer);
}

/** Tooltip when ``isCatalogModelOptionDisabled`` — short label + server ``detail`` when present. */
export function catalogModelOptionUnreachableTitle(
  row: ModelRow,
  agentlayer: ModelCatalogAgentlayer | null
): string {
  const key = catalogProviderKey(row.owned_by);
  const label =
    key === "ollama"
      ? "Ollama"
      : key === "llama_cpp"
        ? "Llama.cpp"
        : (row.owned_by ?? "Model provider").trim() || "Model provider";
  let detail = "";
  if (key === "ollama") {
    detail = (agentlayer?.ollama?.detail ?? "").trim();
  } else if (key === "llama_cpp") {
    detail = (agentlayer?.llama_cpp?.detail ?? "").trim();
    if (detail === "not_configured") detail = "";
  }
  const auth =
    key === "llama_cpp" ? (agentlayer?.llama_cpp?.auth_hint ?? "").trim() : "";
  const base = detail ? `${label} unreachable (${detail})` : `${label} unreachable`;
  if (auth && key === "llama_cpp" && isProviderCatalogUnreachable("llama_cpp", agentlayer)) {
    return `${base}. ${auth}`;
  }
  return base;
}

export async function fetchModelCatalog(): Promise<{
  rows: ModelRow[];
  agentlayer: ModelCatalogAgentlayer | null;
}> {
  try {
    const r = await fetch("/v1/models");
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
      rows.push({
        id: id.trim(),
        owned_by: typeof ob === "string" ? ob : undefined,
      });
    }
    return { rows, agentlayer: raw.agentlayer ?? null };
  } catch {
    return { rows: [], agentlayer: null };
  }
}

export function formatModelCatalogHint(
  agentlayer: ModelCatalogAgentlayer | null,
  opts?: { /** Omit lines that duplicate disabled-row tooltips (any known down provider). */ excludeUnreachableProviderHints?: boolean }
): string | null {
  if (!agentlayer) {
    return "Could not load model catalog (network or server error).";
  }
  const ex = opts?.excludeUnreachableProviderHints === true;
  const msgs: string[] = [];
  const o = agentlayer.ollama;
  if (o && o.reachable === false && !(ex && isProviderCatalogUnreachable("ollama", agentlayer))) {
    const d = (o.detail ?? "").trim();
    msgs.push(d ? `Ollama unreachable (${d})` : "Ollama unreachable");
  }
  const l = agentlayer.llama_cpp;
  if (
    l?.configured &&
    l.reachable === false &&
    l.detail &&
    l.detail !== "not_configured" &&
    !(ex && isProviderCatalogUnreachable("llama_cpp", agentlayer))
  ) {
    msgs.push(`Llama.cpp: ${l.detail}`);
  }
  const authHint = agentlayer.llama_cpp?.auth_hint;
  if (typeof authHint === "string" && authHint.trim()) {
    if (!(ex && isProviderCatalogUnreachable("llama_cpp", agentlayer))) {
      msgs.push(authHint.trim());
    }
  }
  if (msgs.length === 0) return null;
  return msgs.join(" · ");
}

export function modelOptionLabel(row: ModelRow): string {
  const raw = row.owned_by?.trim();
  if (!raw) return row.id;
  const ob = raw.toLowerCase();
  if (ob === "ollama") return row.id;
  if (ob === "llama_cpp") return `${row.id} (llama.cpp)`;
  return `${row.id} (${raw})`;
}

/**
 * ``owned_by`` from the catalog row for this model id (after normalization), or undefined if unknown.
 * Does not invent a default provider — missing ``owned_by`` means the client omits the routing hint.
 */
export function catalogOwnedByForModel(rows: ModelRow[], modelId: string): string | undefined {
  const id = modelId.trim();
  if (!id) return undefined;
  const hit = rows.find((r) => r.id === id);
  const ob = hit?.owned_by;
  if (typeof ob !== "string" || !ob.trim()) return undefined;
  return normalizeCatalogRoutingToken(ob);
}
