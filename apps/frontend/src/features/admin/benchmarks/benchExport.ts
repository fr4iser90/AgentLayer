import type { BenchmarkRun, BenchmarkScenarioResult } from "./benchmarksApi";

/** Mirrors ``bench_workspace_suffix`` on benchmark scenarios (failures export only). */
const WORKSPACE_SUFFIX_BY_SCENARIO: Record<string, string> = {
  C1_bench_marker_file: "coding",
  C2_small_edit: "c2",
  W1_git_readme_no_index: "git",
  W2_find_octocat_no_index: "git",
  W2_find_octocat_indexed: "git",
  SEC1_scan_agentlayer: "agentlayer",
  SEC2_remediate_agentlayer: "agentlayer",
};

function expectedWorkspaceName(scenarioId: string, resourcePrefix: string | undefined): string {
  const suffix = WORKSPACE_SUFFIX_BY_SCENARIO[scenarioId];
  if (!suffix || !resourcePrefix?.trim()) return "";
  return `${resourcePrefix.trim()}${suffix}`;
}

function workspaceCreateNameFromToolRounds(
  rounds: NonNullable<
    NonNullable<BenchmarkScenarioResult["run_metrics"]>["bench_diagnostics"]
  >["tool_rounds"],
): string {
  if (!rounds?.length) return "";
  for (const row of rounds) {
    const name = String(row.name || "").trim().toLowerCase();
    if (name !== "workspace.create" && name !== "workspaces.create" && name !== "create") {
      continue;
    }
    const norm = row.normalized_arguments;
    if (norm && typeof norm === "object" && norm.name != null) {
      const nm = String(norm.name).trim();
      if (nm) return nm;
    }
    const wire = row.wire_arguments;
    if (wire && typeof wire === "object" && !Array.isArray(wire) && "name" in wire) {
      const nm = String((wire as { name?: unknown }).name ?? "").trim();
      if (nm) return nm;
    }
    if (typeof wire === "string" && wire.trim()) {
      try {
        const parsed = JSON.parse(wire) as { name?: unknown };
        const nm = String(parsed.name ?? "").trim();
        if (nm) return nm;
      } catch {
        return wire.trim().slice(0, 200);
      }
    }
  }
  return "";
}

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

export type BenchFailureDebugFields = {
  agent_id: string;
  effective_agent_id: string;
  forwarded_tool_count: number | "";
  forwarded_tools: string;
  assistant_excerpt: string;
  expected_workspace_name: string;
  workspace_create_name: string;
  delegate_call_count: number;
  subagent_start_count: number;
  ws_errors: string;
  report_summary: string;
  blocked_phase: string;
  blocked_detail: string;
  subagent_agents: string;
  subagent_steps: string;
  parent_tool_rounds_json: string;
  report: Record<string, unknown>;
};

export type BenchFailureExportRow = BenchExportRow & BenchFailureDebugFields;

function buildFailureExportReport(
  res: BenchmarkScenarioResult,
): Record<string, unknown> {
  const diag = res.run_metrics?.bench_diagnostics;
  const toolRounds = diag?.tool_rounds ?? [];
  const timeline = diag?.timeline_tail ?? [];
  const subagents = (diag?.subagents as Array<Record<string, unknown>> | undefined) ?? [];
  const insights = diag?.insights ?? [];
  const transport = (res.transport_error || res.error || "").trim();
  const rubric = (res.rubric_failure_reason || "").trim();

  const parentTools = toolRounds.map((row) => {
    const out: Record<string, unknown> = {
      round: row.round,
      name: row.name,
    };
    if (row.ok === true) out.ok = true;
    else if (row.ok === false) out.ok = false;
    else if (row.rejected) out.rejected = true;
    if (row.summary) out.summary = String(row.summary).slice(0, 160);
    if (row.error) out.error = String(row.error).slice(0, 300);
    if (row.result_display) out.result_display = String(row.result_display).slice(0, 300);
    if (row.normalized_arguments && Object.keys(row.normalized_arguments).length > 0) {
      out.normalized_arguments = row.normalized_arguments;
    }
    return out;
  });

  const lastTimeline = timeline.length ? timeline[timeline.length - 1] : null;
  let blockedPhase = String(diag?.blocked_phase || "");
  let blockedDetail = String(diag?.blocked_detail || "");
  if (!blockedPhase && lastTimeline && typeof lastTimeline === "object") {
    const lt = String(lastTimeline.type || "");
    if (lt === "agent.subagent_step") {
      blockedPhase = "subagent_tool";
      blockedDetail = `${String(lastTimeline.tool || "tool")} (${String(lastTimeline.phase || "step")})`;
    } else if (lt === "agent.subagent_start") {
      blockedPhase = "subagent_starting";
      blockedDetail = String(lastTimeline.agent_id || "");
    } else if (lt === "agent.tool_start" || lt === "agent.tool_done") {
      blockedPhase = "parent_tool";
      blockedDetail = String(lastTimeline.tool || lt);
    }
  }

  const summaryParts: string[] = [];
  if (transport) summaryParts.push(transport);
  if (rubric && rubric !== transport) summaryParts.push(`Rubric: ${rubric}`);
  if (blockedPhase) {
    summaryParts.push(`Blocked in ${blockedPhase}${blockedDetail ? ` (${blockedDetail})` : ""}`);
  }
  if (parentTools.length) {
    summaryParts.push(`Parent tools: ${parentTools.map((r) => String(r.name || "?")).join(", ")}`);
  }
  for (const sa of subagents) {
    const aid = String(sa.agent_id || "subagent");
    const steps = Array.isArray(sa.steps) ? sa.steps : [];
    summaryParts.push(`Subagent ${aid}: ${steps.length} step(s)`);
  }
  if (insights.length) summaryParts.push(String(insights[0]).slice(0, 240));

  const stream = diag?.llm_stream;
  let streamTail: string | null = null;
  if (stream?.reasoning) streamTail = String(stream.reasoning).trim().slice(-400);
  else if (stream?.text) streamTail = String(stream.text).trim().slice(-400);

  return {
    summary: summaryParts.join(" · ").slice(0, 1200),
    blocked_phase: blockedPhase || null,
    blocked_detail: blockedDetail || null,
    parent_tool_rounds: parentTools,
    subagents,
    timeline_tail: timeline.slice(-16),
    event_counts: diag?.event_counts ?? {},
    insights: insights.slice(0, 8),
    ws_errors: diag?.ws_errors?.slice(-5) ?? [],
    llm_stream_tail: streamTail,
    assistant_excerpt: String(res.assistant_excerpt || "").trim().slice(0, 500) || null,
  };
}

function failureDebugFields(
  res: BenchmarkScenarioResult,
  resourcePrefix?: string,
): BenchFailureDebugFields {
  const diag = res.run_metrics?.bench_diagnostics;
  const session = diag?.session;
  const toolRounds = diag?.tool_rounds ?? [];
  const forwarded = (session?.forwarded_tools ?? []).map((n) => String(n).trim()).filter(Boolean);
  const forwardedHead = forwarded.slice(0, 24).join(", ");
  const wsErrors = (diag?.ws_errors ?? [])
    .slice(-3)
    .map((row) => {
      const typ = String(row.type || "").trim();
      const detail = String(row.detail || "").trim();
      const chunk = detail ? `${typ}: ${detail}` : typ;
      return chunk.slice(0, 180);
    })
    .filter(Boolean)
    .join(" | ");

  const report = buildFailureExportReport(res);
  const subagents = (report.subagents as Array<Record<string, unknown>> | undefined) ?? [];
  const subagentIds = subagents
    .map((sa) => String(sa.agent_id || "").trim())
    .filter(Boolean);
  const subagentStepsLines: string[] = [];
  for (const sa of subagents) {
    const aid = String(sa.agent_id || "subagent");
    for (const step of Array.isArray(sa.steps) ? sa.steps : []) {
      if (!step || typeof step !== "object") continue;
      const s = step as Record<string, unknown>;
      const tool = String(s.tool || "?");
      const phase = String(s.phase || "?");
      const ok = s.ok;
      const okS = ok === undefined ? "" : ok ? " ok" : " FAIL";
      const err = String(s.error || "").trim();
      let line = `${aid}/${tool} ${phase}${okS}`;
      if (err) line += `: ${err.slice(0, 80)}`;
      subagentStepsLines.push(line);
    }
  }

  return {
    agent_id: String(res.agent_id || ""),
    effective_agent_id: String(session?.effective_agent_id || ""),
    forwarded_tool_count: session?.forwarded_tool_count ?? "",
    forwarded_tools:
      forwarded.length > 24 ? `${forwardedHead} (+${forwarded.length - 24})` : forwardedHead,
    assistant_excerpt: String(res.assistant_excerpt || "").trim().slice(0, 500),
    expected_workspace_name: expectedWorkspaceName(res.scenario_id, resourcePrefix),
    workspace_create_name: workspaceCreateNameFromToolRounds(toolRounds),
    delegate_call_count: toolRounds.filter(
      (r) => String(r.name || "").trim().toLowerCase() === "delegate",
    ).length,
    subagent_start_count: Number(diag?.event_counts?.subagent_start_count ?? 0),
    ws_errors: wsErrors,
    report_summary: String(report.summary || ""),
    blocked_phase: String(report.blocked_phase || ""),
    blocked_detail: String(report.blocked_detail || ""),
    subagent_agents: subagentIds.join(", "),
    subagent_steps: subagentStepsLines.slice(0, 12).join(" | "),
    parent_tool_rounds_json: JSON.stringify(report.parent_tool_rounds ?? []).slice(0, 4000),
    report,
  };
}

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

export function failureExportRow(
  res: BenchmarkScenarioResult,
  resourcePrefix?: string,
): BenchFailureExportRow {
  return { ...scenarioExportRow(res), ...failureDebugFields(res, resourcePrefix) };
}

export function failuresFromResults(
  results: BenchmarkScenarioResult[],
  resourcePrefix?: string,
): BenchFailureExportRow[] {
  return results
    .filter((r) => !r.skipped && !r.passed)
    .map((r) => failureExportRow(r, resourcePrefix));
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

const FAILURE_DEBUG_COLUMNS: (keyof BenchFailureDebugFields)[] = [
  "agent_id",
  "effective_agent_id",
  "forwarded_tool_count",
  "forwarded_tools",
  "assistant_excerpt",
  "expected_workspace_name",
  "workspace_create_name",
  "delegate_call_count",
  "subagent_start_count",
  "report_summary",
  "blocked_phase",
  "blocked_detail",
  "subagent_agents",
  "subagent_steps",
  "parent_tool_rounds_json",
  "ws_errors",
];

const FAILURE_EXPORT_COLUMNS: (keyof BenchFailureExportRow)[] = [
  ...EXPORT_COLUMNS,
  ...FAILURE_DEBUG_COLUMNS,
];

export function resultsToCsv(rows: BenchExportRow[]): string {
  const header = EXPORT_COLUMNS.join(",");
  const body = rows
    .map((row) => EXPORT_COLUMNS.map((col) => csvEscape(row[col] ?? "")).join(","))
    .join("\n");
  return `${header}\n${body}\n`;
}

export function failuresToCsv(rows: BenchFailureExportRow[]): string {
  const header = FAILURE_EXPORT_COLUMNS.join(",");
  const body = rows
    .map((row) => FAILURE_EXPORT_COLUMNS.map((col) => csvEscape(row[col] ?? "")).join(","))
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
  const resourcePrefix = run.resource_prefix || undefined;
  const prefix = (run.resource_prefix || run.id).replace(/[^\w.-]+/g, "_");
  if (failuresOnly) {
    const rows = failuresFromResults(results, resourcePrefix);
    downloadBlob(`${prefix}-failures.csv`, failuresToCsv(rows), "text/csv;charset=utf-8");
    return;
  }
  downloadBlob(`${prefix}-all.csv`, resultsToCsv(results.map(scenarioExportRow)), "text/csv;charset=utf-8");
}

export function downloadFailuresJson(run: BenchmarkRun) {
  const results = run.report_json?.results ?? [];
  const failures = failuresFromResults(results, run.resource_prefix || undefined);
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
