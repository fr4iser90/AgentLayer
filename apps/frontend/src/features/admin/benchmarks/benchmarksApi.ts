import type { AuthContextValue } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

function apiErrorDetail(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean)
      .join("; ");
  }
  return fallback;
}

async function readJsonResponse<T>(res: Response, fallback: string): Promise<T> {
  const text = await res.text();
  if (!text.trim()) {
    if (!res.ok) throw new Error(fallback);
    return {} as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(!res.ok ? fallback : "Invalid JSON response from server");
  }
}

export type BenchmarkScenario = {
  id: string;
  tier: number;
  title: string;
  summary: string;
  prompt: string;
  prompt_template?: string;
  prompts?: Record<string, string>;
  prompt_locale?: string;
  available_locales?: string[];
  rubric: string;
  agent_id: string;
  execution?: string;
  requires: string[];
  expected_tools: string[];
  skip_without_env?: string | null;
};

export type BenchmarkFixture = {
  id: string;
  title: string;
  summary: string;
  optional: boolean;
  requires: string[];
  env_hint?: string | null;
};

export type BenchmarkSuite = {
  id: string;
  label: string;
  description?: string;
  manifest: string;
  tier_max?: number;
  defaults?: Record<string, unknown>;
  scenarios?: BenchmarkScenario[];
  fixtures?: BenchmarkFixture[];
  manifest_fixtures?: string[];
};

export type BenchmarkProfileInput = {
  label?: string;
  model?: string;
  agent_id?: string;
  endpoint_id?: number;
  base_url?: string;
  api_key?: string;
  api_header_name?: string;
  catalog_owned_by?: string;
};

export type BenchmarkRunConfig = {
  profiles?: BenchmarkProfileInput[];
  scenarios?: string[] | null;
  fixtures?: string[] | null;
  tier_max?: number | null;
  run_as_user_id?: string | null;
  friend_user_id?: string | null;
  admin_user_id?: string | null;
  scenario_timeout_sec?: number | null;
  max_tool_rounds_override?: number | null;
  prompt_locale?: string | null;
};

export type AdminUserRow = {
  id: string;
  email?: string | null;
  role: string;
  display_name?: string | null;
  tenant_id?: number;
  tenant_name?: string | null;
};

export type BenchmarkRunReadiness = {
  user_id: string;
  email: string;
  role: string;
  secrets_enabled: boolean;
  secrets: {
    gmail?: boolean;
    ssc_api_key?: boolean;
  };
  workspace_quota?: number;
  benchmark_workspace_quota?: number;
  workspace_count?: number;
  bench_workspace_count?: number;
  non_bench_workspace_count?: number;
  workspace_headroom?: number;
  benchmark_workspace_headroom?: number;
  has_workspace_headroom?: boolean;
  has_benchmark_workspace_headroom?: boolean;
  dashboard_count?: number;
  bench_dashboard_count?: number;
  conversation_count?: number;
  bench_conversation_count?: number;
  has_bench_sandbox_resources?: boolean;
};

export type BenchmarkRunSummary = {
  passed?: number;
  executed?: number;
  total?: number;
  skipped?: number;
};

export type BenchmarkInFlight = {
  scenario_id: string;
  profile_label: string;
  model?: string;
  catalog_owned_by?: string;
  agent_id?: string;
  started_at?: string;
  phase?: string;
  detail?: string;
  llm_round_count?: number;
  current_llm_round?: number;
  tool_call_count?: number;
  tool_names?: string[];
  elapsed_ms?: number;
  provider_prompt_tokens?: number;
  context_window_tokens?: number;
  forwarded_tool_count?: number;
  routed_category?: string;
  llm_text_chars?: number;
  llm_reasoning_chars?: number;
  generation_preview?: string;
};

export type BenchmarkScenarioResult = {
  scenario_id: string;
  profile_label: string;
  model?: string;
  catalog_owned_by?: string;
  agent_id?: string;
  passed: boolean;
  skipped?: boolean;
  score: number;
  latency_ms: number;
  tool_call_count: number;
  tool_names?: string[];
  failure_reason?: string | null;
  rubric_failure_reason?: string | null;
  transport_error?: string | null;
  error?: string | null;
  agent_run_id?: string | null;
  assistant_excerpt?: string;
  scenario_prompt?: string;
  assistant_content?: string;
  assistant_content_truncated?: boolean;
  run_metrics?: {
    compaction_count?: number;
    compaction_events?: Array<{ phase?: string; round?: number; reason?: string }>;
    llm_round_count?: number;
    context_utilization_pct?: number | null;
    total_tokens?: number | null;
    context_snapshot?: Record<string, unknown>;
    timeline_summary?: Array<Record<string, unknown>>;
    tool_invocations?: Array<Record<string, unknown>>;
    capture_mode?: string;
    project_run_status?: string;
    http_status?: number;
    bench_diagnostics?: {
      ws_event_count?: number;
      ws_errors?: Array<{ type?: string; detail?: string; http_status?: number }>;
      timeline_tail?: Array<Record<string, unknown>>;
      event_counts?: Record<string, number>;
      compaction_count_live?: number;
      tool_rounds?: Array<{
        round?: number;
        name?: string;
        summary?: string | null;
        rejected?: boolean;
        ok?: boolean | null;
        error?: string;
        result_chars?: number;
        wire_arguments?: string;
        normalized_arguments?: Record<string, unknown>;
        validation?: {
          missing_or_empty?: string[];
          schema_required?: string[];
          any_of_required?: string[];
          received_arguments?: Record<string, unknown>;
        };
        promoted_full_schema?: boolean;
      }>;
      schema_rounds?: Array<{
        round?: number;
        full_schema_tools?: string[];
      }>;
      agent_run_id_ws?: string;
      insights?: string[];
      llm_stream?: {
        text?: string;
        reasoning?: string;
        text_chars?: number;
        reasoning_chars?: number;
        text_truncated?: boolean;
        reasoning_truncated?: boolean;
        last_round?: number;
      };
      session?: {
        forwarded_tool_count?: number | null;
        forwarded_tools?: string[] | null;
        routed_category?: string;
        effective_agent_id?: string;
        effective_model?: string;
      };
    };
    provider_cache?: {
      cache_prompt_disabled?: boolean;
      cached_prompt_tokens?: number;
    };
    provider_cached_prompt_tokens?: number | null;
    provider_cache_prompt_disabled?: boolean | null;
  } | null;
};

export type BenchmarkSandboxCleanup = {
  before?: {
    workspace_count?: number;
    bench_workspace_count?: number;
    bench_dashboard_count?: number;
    bench_conversation_count?: number;
  };
  after?: {
    workspace_count?: number;
    bench_workspace_count?: number;
    bench_dashboard_count?: number;
    bench_conversation_count?: number;
  };
  deleted?: { workspaces?: number; dashboards?: number; conversations?: number };
  run_prefix_deleted?: { workspaces?: number; dashboards?: number; conversations?: number };
  workspace_headroom?: number;
  has_workspace_headroom?: boolean;
  error?: string;
};

/** @deprecated use BenchmarkSandboxCleanup */
export type BenchmarkWorkspaceCleanup = BenchmarkSandboxCleanup;

export type BenchmarkRun = {
  id: string;
  status: string;
  suite: string;
  user_id?: string | null;
  manifest_path?: string;
  profiles_json?: BenchmarkProfileInput[] | BenchmarkRunConfig;
  summary_json?: BenchmarkRunSummary | null;
  error_text?: string | null;
  resource_prefix?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string;
  report_json?: {
    results?: BenchmarkScenarioResult[];
    in_flight?: BenchmarkInFlight | null;
    bench_cleanup?: BenchmarkWorkspaceCleanup | null;
    bench_cleanup_finish?: BenchmarkWorkspaceCleanup | null;
  } | null;
};

export type BenchmarkLlmProvider = {
  catalog_owned_by: string;
  label: string;
  base_url: string;
  source: "env" | "db" | string;
  endpoint_id?: number | null;
  model_default?: string | null;
  model_agent?: string | null;
  model_coding?: string | null;
};

export type ExternalLlmEndpoint = {
  id: number;
  label: string;
  base_url: string;
  enabled?: boolean;
  api_key_configured: boolean;
  model_default?: string | null;
  model_agent?: string | null;
};

export function autoFixtureIds(
  suite: BenchmarkSuite,
  scenarioIds: ReadonlySet<string>
): Set<string> {
  const ids = new Set(suite.manifest_fixtures ?? []);
  for (const sc of suite.scenarios ?? []) {
    if (scenarioIds.has(sc.id)) {
      sc.requires.forEach((r) => ids.add(r));
    }
  }
  return ids;
}

export function resolveRunProfiles(
  profilesJson: BenchmarkRun["profiles_json"]
): BenchmarkProfileInput[] {
  if (!profilesJson) return [];
  if (Array.isArray(profilesJson)) return profilesJson;
  return profilesJson.profiles ?? [];
}

export async function fetchBenchmarkSuites(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<BenchmarkSuite[]> {
  const res = await apiFetch("/v1/admin/benchmarks/suites", auth);
  const data = await readJsonResponse<{ suites?: BenchmarkSuite[]; detail?: unknown }>(
    res,
    `Failed to load suites (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.suites ?? [];
}

export async function fetchBenchmarkCatalog(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<{ scenarios: BenchmarkScenario[]; fixtures: BenchmarkFixture[]; available_locales: string[] }> {
  const res = await apiFetch("/v1/admin/benchmarks/catalog", auth);
  const data = await readJsonResponse<{
    scenarios?: BenchmarkScenario[];
    fixtures?: BenchmarkFixture[];
    available_locales?: string[];
    detail?: unknown;
  }>(res, `Failed to load catalog (HTTP ${res.status})`);
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return {
    scenarios: data.scenarios ?? [],
    fixtures: data.fixtures ?? [],
    available_locales: data.available_locales ?? ["en"],
  };
}

export function benchmarkScenarioPrompt(sc: BenchmarkScenario, locale: string): string {
  const loc = locale.trim().toLowerCase() || "en";
  return sc.prompts?.[loc] ?? sc.prompt ?? sc.prompt_template ?? "";
}

export async function fetchBenchmarkRuns(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  limit = 40
): Promise<BenchmarkRun[]> {
  const res = await apiFetch(`/v1/admin/benchmarks/runs?limit=${limit}`, auth);
  const data = await readJsonResponse<{ runs?: BenchmarkRun[]; detail?: unknown }>(
    res,
    `Failed to load runs (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.runs ?? [];
}

export async function fetchBenchmarkRun(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  runId: string
): Promise<BenchmarkRun> {
  const res = await apiFetch(`/v1/admin/benchmarks/runs/${encodeURIComponent(runId)}`, auth);
  const data = await readJsonResponse<{ run?: BenchmarkRun; detail?: unknown }>(
    res,
    `Failed to load run (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.run as BenchmarkRun;
}

export async function deleteBenchmarkRun(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  runId: string
): Promise<void> {
  const res = await apiFetch(`/v1/admin/benchmarks/runs/${encodeURIComponent(runId)}`, auth, {
    method: "DELETE",
  });
  const data = await readJsonResponse<{ detail?: unknown }>(
    res,
    `Failed to delete run (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
}

export type StartBenchmarkBody = {
  suite: string;
  profiles: BenchmarkProfileInput[];
  scenarios?: string[];
  fixtures?: string[];
  tier_max?: number;
  run_as_user_id?: string;
  friend_user_id?: string;
  scenario_timeout_sec?: number;
  max_tool_rounds_override?: number;
  retain_workspaces?: boolean;
  prompt_locale?: string;
};

export function userOptionLabel(u: AdminUserRow): string {
  const name = (u.email || u.display_name || u.id).trim();
  const tenant = u.tenant_name?.trim();
  return tenant ? `${name} · ${u.role} · ${tenant}` : `${name} · ${u.role}`;
}

export async function fetchAdminUsers(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<AdminUserRow[]> {
  const res = await apiFetch("/v1/admin/users", auth);
  const data = await readJsonResponse<{ users?: AdminUserRow[]; detail?: unknown }>(
    res,
    `Failed to load users (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.users ?? [];
}

export async function cleanupBenchmarkResources(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  userId: string
): Promise<BenchmarkRunReadiness & { cleanup?: BenchmarkSandboxCleanup }> {
  const res = await apiFetch(
    `/v1/admin/benchmarks/cleanup-resources?user_id=${encodeURIComponent(userId)}`,
    auth,
    { method: "POST" }
  );
  const data = await readJsonResponse<
    BenchmarkRunReadiness & { cleanup?: BenchmarkSandboxCleanup; detail?: unknown }
  >(res, `Failed to clean benchmark sandboxes (HTTP ${res.status})`);
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data;
}

/** @deprecated use cleanupBenchmarkResources */
export const cleanupBenchmarkWorkspaces = cleanupBenchmarkResources;

export async function fetchBenchmarkRunReadiness(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  userId: string
): Promise<BenchmarkRunReadiness> {
  const res = await apiFetch(
    `/v1/admin/benchmarks/run-readiness?user_id=${encodeURIComponent(userId)}`,
    auth
  );
  const data = await readJsonResponse<BenchmarkRunReadiness & { detail?: unknown }>(
    res,
    `Failed to load readiness (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data;
}

export async function startBenchmarkRun(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  body: StartBenchmarkBody
): Promise<BenchmarkRun> {
  const res = await apiFetch("/v1/admin/benchmarks/runs", auth, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const data = await readJsonResponse<{ run?: BenchmarkRun; detail?: unknown }>(
    res,
    `Failed to start benchmark (HTTP ${res.status})`
  );
  if (!res.ok) {
    throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  }
  return data.run as BenchmarkRun;
}

export async function cancelBenchmarkRun(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  runId: string
): Promise<void> {
  const res = await apiFetch(
    `/v1/admin/benchmarks/runs/${encodeURIComponent(runId)}/cancel`,
    auth,
    { method: "POST" }
  );
  const data = await readJsonResponse<{ detail?: unknown }>(
    res,
    `Failed to cancel benchmark (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
}

export async function fetchBenchmarkLlmProviders(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<BenchmarkLlmProvider[]> {
  const res = await apiFetch("/v1/admin/benchmarks/llm-providers", auth);
  const data = await readJsonResponse<{ providers?: BenchmarkLlmProvider[]; detail?: unknown }>(
    res,
    `Failed to load LLM providers (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.providers ?? [];
}

export async function fetchExternalLlmEndpoints(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<ExternalLlmEndpoint[]> {
  const res = await apiFetch("/v1/admin/external-llm/endpoints", auth);
  const data = (await res.json()) as { endpoints?: ExternalLlmEndpoint[] };
  return data.endpoints ?? [];
}
