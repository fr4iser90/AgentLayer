/**
 * ``scheduler_jobs.execution_target`` = registry ``agent_id`` (``plugins/agents``).
 * Load options from ``GET /v1/user/scheduler-jobs/execution-targets``.
 */

export const EXECUTION_GENERAL = "general";
export const EXECUTION_CODING = "coding";

export type ExecutionTargetCatalogRow = {
  value: string;
  label: string;
  agent_id: string;
  requires_workspace?: boolean;
  min_role?: string;
};

/** Empty until catalog API loads. */
export const EXECUTION_TARGET_OPTIONS: ExecutionTargetCatalogRow[] = [];

export function executionTargetKnownValues(
  catalog: readonly ExecutionTargetCatalogRow[]
): ReadonlySet<string> {
  return new Set(catalog.map((o) => o.value).filter(Boolean));
}

export function parseSchedulesBlockExecutionTargetFilter(
  raw: string | undefined | null,
  knownValues: ReadonlySet<string>
): "all" | string {
  const t = String(raw ?? "all").trim().toLowerCase();
  if (!t || t === "all") return "all";
  if (knownValues.has(t)) return t;
  return "all";
}

export function catalogRowForExecutionTarget(
  target: string,
  catalog: readonly ExecutionTargetCatalogRow[]
): ExecutionTargetCatalogRow | undefined {
  const t = normalizeExecutionTargetInput(target, catalog);
  return catalog.find((o) => o.value === t);
}

export function agentIdForExecutionTarget(
  target: string,
  catalog: readonly ExecutionTargetCatalogRow[] = EXECUTION_TARGET_OPTIONS
): string {
  const row = catalogRowForExecutionTarget(target, catalog);
  return row?.agent_id ?? normalizeExecutionTargetInput(target, catalog);
}

export function labelForExecutionTarget(
  target: string,
  catalog: readonly ExecutionTargetCatalogRow[] = EXECUTION_TARGET_OPTIONS
): string {
  const row = catalogRowForExecutionTarget(target, catalog);
  if (row) return row.label;
  return (target || "").trim() || "—";
}

export function normalizeExecutionTargetInput(
  target: string,
  catalog: readonly ExecutionTargetCatalogRow[] = EXECUTION_TARGET_OPTIONS
): string {
  const t = (target || "").trim().toLowerCase();
  const hit = catalog.find((o) => o.value === t);
  if (hit) return hit.value;
  return t || EXECUTION_GENERAL;
}

export function executionTargetRequiresWorkspace(
  target: string,
  catalog: readonly ExecutionTargetCatalogRow[]
): boolean {
  const row = catalogRowForExecutionTarget(target, catalog);
  return Boolean(row?.requires_workspace);
}
