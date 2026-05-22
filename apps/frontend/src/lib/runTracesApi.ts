import { apiFetch } from "./api";
import type { AuthContextValue } from "../auth/AuthContext";

export type RunTrace = {
  id: string;
  agent_id?: string | null;
  status: string;
  task_id?: string | null;
  parent_run_id?: string | null;
  started_at?: string;
  finished_at?: string | null;
  embedded_subagent?: boolean;
};

export async function fetchAdminRuns(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  limit = 40
): Promise<RunTrace[]> {
  const res = await apiFetch(`/v1/admin/run-traces/runs?limit=${limit}`, auth);
  const data = (await res.json()) as { runs?: RunTrace[] };
  return data.runs ?? [];
}

export async function fetchAdminRunTrace(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  runId: string
): Promise<{
  run: RunTrace;
  tool_invocations: Record<string, unknown>[];
  child_runs: RunTrace[];
}> {
  const res = await apiFetch(`/v1/admin/run-traces/runs/${encodeURIComponent(runId)}`, auth);
  return (await res.json()) as {
    run: RunTrace;
    tool_invocations: Record<string, unknown>[];
    child_runs: RunTrace[];
  };
}
