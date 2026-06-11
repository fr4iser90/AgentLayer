import type { BenchmarkScenarioResult } from "./benchmarksApi";
import { scenarioExportRow } from "./benchExport";

function resolveScenarioResponse(res: BenchmarkScenarioResult): string {
  const direct = (res.assistant_content || res.assistant_excerpt || "").trim();
  if (direct) return direct;
  const stream = res.run_metrics?.bench_diagnostics?.llm_stream;
  if (!stream) return "";
  const parts: string[] = [];
  if (stream.reasoning?.trim()) parts.push(stream.reasoning.trim());
  if (stream.text?.trim()) parts.push(stream.text.trim());
  return parts.join("\n\n");
}

function formatProviderModel(res: BenchmarkScenarioResult): string {
  const provider = (res.profile_label || res.catalog_owned_by || "").trim();
  const model = (res.model || "").trim();
  if (provider && model) return `${provider} / ${model}`;
  return provider || model || "—";
}

function formatToolRoundResult(row: {
  rejected?: boolean;
  ok?: boolean | null;
  error?: string;
}): string {
  if (row.rejected === true) return "rejected (schema)";
  if (row.ok === false) return String(row.error || "failed").trim() || "failed";
  if (row.ok === true) return "ok";
  return "—";
}

function formatToolRoundMissing(row: {
  validation?: {
    missing_or_empty?: string[];
    schema_required?: string[];
  };
}): string {
  if (row.validation?.missing_or_empty?.length) {
    return row.validation.missing_or_empty.join(", ");
  }
  if (row.validation?.schema_required?.length) {
    return `req: ${row.validation.schema_required.join(", ")}`;
  }
  return "—";
}

function section(title: string, body: string): string {
  const trimmed = body.trim();
  if (!trimmed) return "";
  return `${title}\n${trimmed}\n`;
}

/** Plain-text bundle for pasting benchmark scenario diagnostics into chat or tickets. */
export function formatScenarioDetailsForCopy(res: BenchmarkScenarioResult): string {
  const exportRow = scenarioExportRow(res);
  const benchDiag = res.run_metrics?.bench_diagnostics;
  const sessionInfo = benchDiag?.session;
  const llmStream = benchDiag?.llm_stream;
  const ctx = res.run_metrics?.context_snapshot;
  const contextWindow =
    ctx && typeof ctx.context_window_tokens === "number"
      ? ctx.context_window_tokens
      : ctx && typeof ctx.budget_tokens === "number"
        ? ctx.budget_tokens
        : null;

  const status = res.skipped ? "SKIP" : res.passed ? "PASS" : "FAIL";
  const header = [
    exportRow.scenario_id,
    formatProviderModel(res),
    status,
    exportRow.failure_reason || "",
  ]
    .filter(Boolean)
    .join("\t");

  const summary = [
    `${res.tool_call_count ?? 0} tools · ${res.run_metrics?.llm_round_count ?? 0} llm`,
    `${res.run_metrics?.compaction_count ?? 0} compaction`,
    res.run_metrics?.context_utilization_pct != null
      ? `${res.run_metrics.context_utilization_pct}% ctx`
      : "",
    `${Math.round(res.latency_ms ?? 0)} ms`,
  ]
    .filter(Boolean)
    .join("\t");

  const lines: string[] = [header, summary, ""];

  lines.push(section("Prompt", res.scenario_prompt?.trim() || "—"));
  lines.push(section("Assistant response", resolveScenarioResponse(res) || "—"));

  const meta: string[] = [];
  const toolsDisplay =
    (res.tool_names?.length ?? 0) > 0
      ? res.tool_names!.join(", ")
      : exportRow.tools || "none";
  meta.push(`Tools invoked: ${toolsDisplay}`);
  if (res.run_metrics?.capture_mode) {
    meta.push(`Capture: ${res.run_metrics.capture_mode}`);
  }
  if (contextWindow != null) {
    meta.push(`Context window (tokens): ${contextWindow}`);
  }
  if (res.run_metrics?.provider_cache?.cache_prompt_disabled === true) {
    meta.push("Provider prompt cache: off (benchmark)");
  }
  if (typeof res.run_metrics?.provider_cached_prompt_tokens === "number") {
    meta.push(`Provider cached prompt tokens: ${res.run_metrics.provider_cached_prompt_tokens}`);
  }
  if (sessionInfo?.forwarded_tool_count != null) {
    const cat = sessionInfo.routed_category ? ` (${sessionInfo.routed_category})` : "";
    meta.push(`Tools forwarded to model: ${sessionInfo.forwarded_tool_count}${cat}`);
  }
  if (meta.length) lines.push(meta.join("\n"), "");

  if (sessionInfo?.forwarded_tools?.length) {
    lines.push(section("Forwarded tool names", sessionInfo.forwarded_tools.join(", ")));
  }

  if (llmStream?.reasoning || llmStream?.text) {
    lines.push("LLM stream (websocket, persisted)");
    if (llmStream.reasoning) {
      const suffix =
        typeof llmStream.reasoning_chars === "number"
          ? ` · ${llmStream.reasoning_chars} chars`
          : "";
      const trunc = llmStream.reasoning_truncated ? " · truncated in storage" : "";
      lines.push(`Reasoning / thinking${suffix}${trunc}`, llmStream.reasoning, "");
    }
    if (llmStream.text) {
      const suffix =
        typeof llmStream.text_chars === "number" ? ` · ${llmStream.text_chars} chars` : "";
      const trunc = llmStream.text_truncated ? " · truncated in storage" : "";
      lines.push(`Visible text${suffix}${trunc}`, llmStream.text, "");
    }
  }

  if (res.transport_error || res.error) {
    const transport = [res.transport_error || res.error];
    if (res.run_metrics?.http_status != null) {
      transport.push(`HTTP ${res.run_metrics.http_status}`);
    }
    lines.push(section("Transport / timeout", transport.join("\n")));
  }

  if (res.rubric_failure_reason) {
    lines.push(section("Task outcome (rubric)", res.rubric_failure_reason));
  } else if (res.failure_reason && !(res.transport_error || res.error)) {
    lines.push(section("Rubric / outcome", res.failure_reason));
  }

  if (benchDiag?.insights?.length) {
    lines.push(
      section(
        "Why it failed (diagnostics)",
        benchDiag.insights.map((line) => `- ${line}`).join("\n"),
      ),
    );
  }

  const toolRounds = benchDiag?.tool_rounds ?? [];
  if (toolRounds.length) {
    lines.push("Tool rounds (websocket)");
    lines.push("R\tTool\tArguments\tWire args\tMissing\tPromoted\tResult");
    for (const row of toolRounds) {
      const args = String(row.summary || "").trim() || "(empty)";
      const wire =
        row.wire_arguments != null && String(row.wire_arguments).trim()
          ? String(row.wire_arguments).trim()
          : "—";
      lines.push(
        [
          row.round ?? "—",
          row.name || "—",
          args,
          wire,
          formatToolRoundMissing(row),
          row.promoted_full_schema === true ? "yes" : "—",
          formatToolRoundResult(row),
        ].join("\t"),
      );
    }
    lines.push("");
  }

  const schemaRounds = benchDiag?.schema_rounds ?? [];
  if (schemaRounds.length) {
    lines.push(
      section(
        "Full-schema LLM rounds",
        schemaRounds
          .map((sr) => {
            const tools = (sr.full_schema_tools ?? []).join(", ");
            return `round ${sr.round ?? "?"}: ${tools || "—"}`;
          })
          .join("\n"),
      ),
    );
  }

  const traceInvocations = res.run_metrics?.tool_invocations ?? [];
  if (traceInvocations.length) {
    lines.push(
      section(
        "Persisted tool trace",
        traceInvocations
          .map((inv) => {
            const name = String(inv.tool_name || "?");
            const args = inv.args_preview ? ` args=${inv.args_preview}` : "";
            const ok = inv.ok === true ? " ok" : inv.ok === false ? " FAIL" : "";
            const err = inv.result_error ? ` err=${inv.result_error}` : "";
            return `${name}${args}${ok}${err}`;
          })
          .join("\n"),
      ),
    );
  }

  if (benchDiag?.ws_errors?.length) {
    lines.push(
      section(
        "WebSocket errors",
        benchDiag.ws_errors
          .map((row) => {
            const parts = [row.type || "error"];
            if (row.http_status != null) parts.push(`HTTP ${row.http_status}`);
            if (row.detail) parts.push(String(row.detail));
            return parts.join(" · ");
          })
          .join("\n"),
      ),
    );
  }

  if (benchDiag?.timeline_tail?.length) {
    lines.push(
      section(
        "Agent timeline (last events)",
        benchDiag.timeline_tail
          .map((ev) => {
            const typ = String(ev.type || "?");
            const tool = ev.tool ? ` tool=${ev.tool}` : "";
            const round = ev.round != null ? ` round=${ev.round}` : "";
            const phase = ev.phase ? ` phase=${ev.phase}` : "";
            const channel = ev.channel ? ` channel=${String(ev.channel)}` : "";
            const deltaChars = ev.delta_chars != null ? ` +${String(ev.delta_chars)} chars` : "";
            const deltaEvents =
              ev.delta_events != null && Number(ev.delta_events) > 1
                ? ` (${String(ev.delta_events)} chunks)`
                : "";
            const summary = ev.summary ? ` args=${String(ev.summary)}` : "";
            const ok = ev.ok === false ? " FAIL" : ev.ok === true ? " ok" : "";
            const err = ev.error ? ` err=${String(ev.error)}` : "";
            return `${typ}${tool}${round}${phase}${channel}${deltaChars}${deltaEvents}${summary}${ok}${err}`;
          })
          .join("\n"),
      ),
    );
  }

  if (benchDiag?.event_counts) {
    const ec = benchDiag.event_counts;
    lines.push(
      `Event counts: llm=${ec.llm_round_count ?? 0}, tool_start=${ec.tool_start_count ?? 0}, tool_done=${ec.tool_done_count ?? 0}`,
      "",
    );
  }

  const runTraceId = res.agent_run_id || benchDiag?.agent_run_id_ws;
  if (runTraceId) {
    lines.push(`Open run trace · ${runTraceId}`);
  }

  return lines.join("\n").trimEnd();
}

export async function copyScenarioDetailsToClipboard(res: BenchmarkScenarioResult): Promise<void> {
  const text = formatScenarioDetailsForCopy(res);
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("copy failed");
}
