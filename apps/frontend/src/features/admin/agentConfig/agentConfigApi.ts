import type { AuthContextValue } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";
import type { BenchmarkStatsPayload } from "../benchmarks/benchmarksApi";

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
  opts?: { writable_only?: boolean; ui_group?: string; harness_only?: boolean },
): Promise<{ knobs: AgentConfigKnob[]; registry_version?: number }> {
  const qs = new URLSearchParams();
  if (opts?.writable_only) qs.set("writable_only", "true");
  if (opts?.ui_group) qs.set("ui_group", opts.ui_group);
  if (opts?.harness_only !== false) qs.set("harness_only", "true");
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

export type AgentConfigSessionRow = {
  id: string;
  label?: string;
  cohort_label?: string;
  status?: string;
};

export async function fetchAgentConfigSessions(auth: AuthContextValue, limit = 50) {
  const res = await apiFetch(`/v1/admin/agent-config/sessions?limit=${limit}`, auth);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data as { ok?: boolean; sessions?: AgentConfigSessionRow[] };
}

export async function createAgentConfigSession(
  auth: AuthContextValue,
  body: { label: string; cohort_label: string; hypothesis?: string },
) {
  const res = await apiFetch("/v1/admin/agent-config/sessions", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type BenchmarkAnalysisScenario = {
  scenario_id: string;
  pass_rate: number;
  patterns: string[];
};

export type BenchmarkAnalysisPayload = {
  ok?: boolean;
  run_count: number;
  cohort?: string | null;
  fingerprint?: string | null;
  suite?: string | null;
  top_patterns?: Record<string, number>;
  by_scenario?: BenchmarkAnalysisScenario[];
  stats?: BenchmarkStatsPayload;
};

export type BenchmarkCohortRow = {
  cohort_label: string;
  run_count: number;
};

export type BenchmarkExperiment = {
  id: string;
  label: string;
  status?: string;
  hypothesis?: string | null;
  session_id?: string | null;
  fingerprint_at_start?: string | null;
  suite_preset?: string | null;
  harness_preset?: string | null;
  pending_patches_json?: unknown[];
  run_ids_json?: string[];
  created_at?: string;
};

export type BenchmarkReview = {
  id: string;
  verdict?: string;
  summary?: string | null;
  mode?: string;
  reviewer_model?: string | null;
  created_at?: string;
  patterns_json?: Record<string, number>;
};

export type BenchmarkExperimentReport = {
  experiment: BenchmarkExperiment;
  analysis: BenchmarkAnalysisPayload;
  reviews: BenchmarkReview[];
};

export async function fetchBenchmarkExperiments(auth: AuthContextValue, limit = 50) {
  const res = await apiFetch(`/v1/admin/benchmarks/experiments?limit=${limit}`, auth);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data as { ok?: boolean; experiments?: BenchmarkExperiment[] };
}

export async function fetchBenchmarkAnalysis(
  auth: AuthContextValue,
  opts?: {
    cohort?: string;
    fingerprint?: string;
    suite?: string;
    since_days?: number;
    experiment_id?: string;
  },
): Promise<BenchmarkAnalysisPayload> {
  const qs = new URLSearchParams();
  if (opts?.cohort) qs.set("cohort", opts.cohort);
  if (opts?.fingerprint) qs.set("fingerprint", opts.fingerprint);
  if (opts?.suite) qs.set("suite", opts.suite);
  if (opts?.since_days != null) qs.set("since_days", String(opts.since_days));
  if (opts?.experiment_id) qs.set("experiment_id", opts.experiment_id);
  const q = qs.toString();
  const res = await apiFetch(`/v1/admin/benchmarks/analysis${q ? `?${q}` : ""}`, auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchBenchmarkCohorts(auth: AuthContextValue, limit = 200) {
  const res = await apiFetch(`/v1/admin/benchmarks/cohorts?limit=${limit}`, auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ ok?: boolean; cohorts?: BenchmarkCohortRow[] }>;
}

export async function fetchBenchmarkCohortCompare(
  auth: AuthContextValue,
  cohortA: string,
  cohortB: string,
  suite?: string,
) {
  const qs = new URLSearchParams({ cohort_a: cohortA, cohort_b: cohortB });
  if (suite) qs.set("suite", suite);
  const res = await apiFetch(`/v1/admin/benchmarks/cohorts/compare?${qs}`, auth);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{
    ok?: boolean;
    cohort_a: string;
    cohort_b: string;
    a: BenchmarkAnalysisPayload;
    b: BenchmarkAnalysisPayload;
  }>;
}

export async function submitBenchmarkReview(
  auth: AuthContextValue,
  body: {
    experiment_id?: string;
    session_id?: string;
    run_ids?: string[];
    mode?: string;
    summary_hint?: string;
  },
) {
  const res = await apiFetch("/v1/admin/benchmarks/review", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ ok?: boolean; review?: BenchmarkReview }>;
}

export async function fetchBenchmarkExperimentReport(auth: AuthContextValue, experimentId: string) {
  const res = await apiFetch(
    `/v1/admin/benchmarks/experiments/${encodeURIComponent(experimentId)}/report`,
    auth,
  );
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data as { ok?: boolean } & BenchmarkExperimentReport;
}
