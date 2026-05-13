/** GET /v1/models — merged Ollama + llama.cpp; ``agentlayer`` status from backend. */

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
  return row.owned_by === "llama_cpp" ? `${row.id} (llama.cpp)` : row.id;
}
