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

export function formatModelCatalogHint(agentlayer: ModelCatalogAgentlayer | null): string | null {
  if (!agentlayer) {
    return "Could not load model catalog (network or server error).";
  }
  const msgs: string[] = [];
  const o = agentlayer.ollama;
  if (o && o.reachable === false) {
    const d = (o.detail ?? "").trim();
    msgs.push(d ? `Ollama unreachable (${d})` : "Ollama unreachable");
  }
  const l = agentlayer.llama_cpp;
  if (l?.configured && l.reachable === false && l.detail && l.detail !== "not_configured") {
    msgs.push(`Llama.cpp: ${l.detail}`);
  }
  const authHint = agentlayer.llama_cpp?.auth_hint;
  if (typeof authHint === "string" && authHint.trim()) {
    msgs.push(authHint.trim());
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
