import type { BenchmarkRun, BenchmarkScenarioResult } from "./benchmarksApi";

function insightsSummary(res: BenchmarkScenarioResult): string {
  const insights = res.run_metrics?.bench_diagnostics?.insights;
  if (!Array.isArray(insights) || insights.length === 0) return "";
  return insights
    .map((line) => String(line).trim())
    .filter(Boolean)
    .slice(0, 4)
    .join(" | ");
}

function toolsSummary(res: BenchmarkScenarioResult): string {
  const names = res.tool_names ?? [];
  if (names.length === 0) {
    const rounds = res.run_metrics?.bench_diagnostics?.tool_rounds ?? [];
    const fromWs = rounds
      .map((r) => String(r.name || "").trim())
      .filter(Boolean);
    if (fromWs.length === 0) return "";
    const counts = new Map<string, number>();
    for (const n of fromWs) counts.set(n, (counts.get(n) ?? 0) + 1);
    return [...counts.entries()]
      .map(([n, c]) => (c > 1 ? `${n} ×${c}` : n))
      .join(", ");
  }
  const head = names.slice(0, 12).join(", ");
  return names.length > 12 ? `${head} (+${names.length - 12})` : head;
}

export type BenchExportRow = {
  scenario_id: string;
  profile_label: string;
  model: string;
  skipped: boolean;
  passed: boolean;
  transport_error: string;
  rubric_failure: string;
  failure_reason: string;
  insights: string;
  tool_call_count: number;
  tools: string;
  llm_round_count: number | "";
  latency_ms: number;
  agent_run_id: string;
};

export function scenarioExportRow(res: BenchmarkScenarioResult): BenchExportRow {
  const transport =
    (res.transport_error || res.error || "").trim();
  const rubric = (res.rubric_failure_reason || "").trim();
  return {
    scenario_id: res.scenario_id,
    profile_label: res.profile_label,
    model: res.model || "",
    skipped: Boolean(res.skipped),
    passed: res.passed,
    transport_error: transport,
    rubric_failure: rubric,
    failure_reason: (res.failure_reason || transport || rubric).trim(),
    insights: insightsSummary(res),
    tool_call_count: res.tool_call_count ?? 0,
    tools: toolsSummary(res),
    llm_round_count: res.run_metrics?.llm_round_count ?? "",
    latency_ms: Math.round(res.latency_ms ?? 0),
    agent_run_id: res.agent_run_id || res.run_metrics?.bench_diagnostics?.agent_run_id_ws || "",
  };
}

export function failuresFromResults(results: BenchmarkScenarioResult[]): BenchExportRow[] {
  return results.filter((r) => !r.skipped && !r.passed).map(scenarioExportRow);
}

function csvEscape(val: string | number | boolean): string {
  const s = String(val);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

const EXPORT_COLUMNS: (keyof BenchExportRow)[] = [
  "scenario_id",
  "profile_label",
  "model",
  "passed",
  "skipped",
  "transport_error",
  "rubric_failure",
  "failure_reason",
  "insights",
  "tool_call_count",
  "tools",
  "llm_round_count",
  "latency_ms",
  "agent_run_id",
];

export function resultsToCsv(rows: BenchExportRow[]): string {
  const header = EXPORT_COLUMNS.join(",");
  const body = rows
    .map((row) => EXPORT_COLUMNS.map((col) => csvEscape(row[col] ?? "")).join(","))
    .join("\n");
  return `${header}\n${body}\n`;
}

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadFailuresCsv(run: BenchmarkRun, failuresOnly = true) {
  const results = run.report_json?.results ?? [];
  const rows = failuresOnly ? failuresFromResults(results) : results.map(scenarioExportRow);
  const prefix = (run.resource_prefix || run.id).replace(/[^\w.-]+/g, "_");
  const suffix = failuresOnly ? "failures" : "all";
  downloadBlob(`${prefix}-${suffix}.csv`, resultsToCsv(rows), "text/csv;charset=utf-8");
}

export function downloadFailuresJson(run: BenchmarkRun) {
  const results = run.report_json?.results ?? [];
  const failures = failuresFromResults(results);
  const prefix = (run.resource_prefix || run.id).replace(/[^\w.-]+/g, "_");
  const payload = {
    run_id: run.id,
    status: run.status,
    resource_prefix: run.resource_prefix,
    summary: run.summary_json,
    failure_count: failures.length,
    failures,
  };
  downloadBlob(
    `${prefix}-failures.json`,
    JSON.stringify(payload, null, 2),
    "application/json",
  );
}

export function downloadFullReportJson(run: BenchmarkRun) {
  const prefix = (run.resource_prefix || run.id).replace(/[^\w.-]+/g, "_");
  downloadBlob(
    `${prefix}-report.json`,
    JSON.stringify(run.report_json ?? { results: [] }, null, 2),
    "application/json",
  );
}
