import type { AuthContextValue } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

export type AgentConfigKnob = {
  id: string;
  layer?: string;
  ui_group?: string;
  writable?: boolean;
  type?: string;
  effective?: unknown;
  source?: string;
  effective_label?: string;
  doc?: string;
  default?: unknown;
};

/** Layers editable as Harness via agent-config/apply (not rubrics, bench run fields, code). */
const HARNESS_KNOB_LAYERS = new Set(["runtime_config", "agent_yaml", "router_yaml", "operator"]);

export function isHarnessKnob(knob: AgentConfigKnob): boolean {
  return HARNESS_KNOB_LAYERS.has(String(knob.layer || ""));
}

export async function fetchAgentConfigKnobs(
  auth: AuthContextValue,
  opts?: {
    writable_only?: boolean;
    ui_group?: string;
    harness_only?: boolean;
    catalog_owned_by?: string;
    model?: string;
  },
): Promise<{ knobs: AgentConfigKnob[]; registry_version?: number }> {
  const qs = new URLSearchParams();
  if (opts?.writable_only) qs.set("writable_only", "true");
  if (opts?.ui_group) qs.set("ui_group", opts.ui_group);
  if (opts?.harness_only !== false) qs.set("harness_only", "true");
  if (opts?.catalog_owned_by) qs.set("catalog_owned_by", opts.catalog_owned_by);
  if (opts?.model) qs.set("model", opts.model);
  const res = await apiFetch(`/v1/admin/agent-config/knobs?${qs}`, auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchAgentConfigFingerprint(auth: AuthContextValue) {
  const res = await apiFetch("/v1/admin/agent-config/fingerprint", auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function applyAgentConfigPatches(
  auth: AuthContextValue,
  body: {
    patches: { knob_id: string; value: unknown }[];
    hypothesis?: string;
  },
) {
  const res = await apiFetch("/v1/admin/agent-config/apply", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type AgentConfigModelOverride = {
  id: string;
  catalog_owned_by: string;
  model?: string;
  label?: string | null;
  knobs_json?: Record<string, unknown>;
  updated_at?: string;
};

export async function fetchAgentConfigModelOverrides(auth: AuthContextValue) {
  const res = await apiFetch("/v1/admin/agent-config/model-overrides", auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ ok?: boolean; overrides?: AgentConfigModelOverride[] }>;
}

export async function applyAgentConfigModelPatches(
  auth: AuthContextValue,
  body: {
    catalog_owned_by: string;
    model?: string | null;
    label?: string | null;
    override_id?: string | null;
    patches: { knob_id: string; value: unknown }[];
    hypothesis?: string;
  },
) {
  const res = await apiFetch("/v1/admin/agent-config/model-overrides/apply", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteAgentConfigModelOverride(auth: AuthContextValue, overrideId: string) {
  const res = await apiFetch(
    `/v1/admin/agent-config/model-overrides/${encodeURIComponent(overrideId)}`,
    auth,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function initializeAgentConfigDefaults(auth: AuthContextValue, overwrite = false) {
  const qs = overwrite ? "?overwrite=true" : "";
  const res = await apiFetch(`/v1/admin/agent-config/initialize-defaults${qs}`, auth, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchAgentConfigChangelog(auth: AuthContextValue, limit = 30) {
  const res = await apiFetch(`/v1/admin/agent-config/changelog?limit=${limit}`, auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
