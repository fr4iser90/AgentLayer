import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  autoFixtureIds,
  fetchAdminUsers,
  fetchBenchmarkCatalog,
  fetchBenchmarkRun,
  fetchBenchmarkRunReadiness,
  fetchBenchmarkLlmProviders,
  fetchBenchmarkRuns,
  fetchBenchmarkSuites,
  deleteBenchmarkRun,
  cancelBenchmarkRun,
  startBenchmarkRun,
  userOptionLabel,
  type AdminUserRow,
  type BenchmarkFixture,
  type BenchmarkInFlight,
  type BenchmarkLlmProvider,
  type BenchmarkProfileInput,
  type BenchmarkRun,
  type BenchmarkRunReadiness,
  type BenchmarkScenario,
  type BenchmarkScenarioResult,
  type BenchmarkSuite,
} from "../../features/admin/benchmarks/benchmarksApi";
import {
  downloadFailuresCsv,
  downloadFailuresJson,
  downloadFullReportJson,
  failuresFromResults,
  type BenchExportRow,
} from "../../features/admin/benchmarks/benchExport";
import {
  catalogModelIdsForProvider,
  fetchModelCatalog,
  isProviderCatalogUnreachable,
  type ModelCatalogAgentlayer,
  type ModelRow,
} from "../../lib/modelCatalog";
import { ConfirmModal } from "../../components/ConfirmModal";

function defaultProviderModel(p: BenchmarkLlmProvider): string {
  return (p.model_agent || p.model_default || p.model_coding || "").trim();
}

function buildProfilesFromSelection(
  providers: BenchmarkLlmProvider[],
  selectedIds: ReadonlySet<string>,
  modelById: ReadonlyMap<string, string>
): BenchmarkProfileInput[] {
  return providers
    .filter((p) => selectedIds.has(p.catalog_owned_by))
    .map((p) => ({
      catalog_owned_by: p.catalog_owned_by,
      endpoint_id: p.endpoint_id ?? undefined,
      label: p.label || p.catalog_owned_by,
      model: (modelById.get(p.catalog_owned_by) || defaultProviderModel(p)).trim(),
    }))
    .filter((p) => p.model.length > 0);
}

function resolveInitialProviderModel(
  p: BenchmarkLlmProvider,
  catalogRows: ModelRow[],
  previous: string | undefined
): string {
  const catalogIds = catalogModelIdsForProvider(catalogRows, p.catalog_owned_by);
  const envDefault = defaultProviderModel(p);
  const current = (previous ?? envDefault).trim();
  if (current && catalogIds.includes(current)) return current;
  if (envDefault && catalogIds.includes(envDefault)) return envDefault;
  if (catalogIds.length > 0) return catalogIds[0];
  return current || envDefault;
}

function formatBenchmarkProviderModel(res: BenchmarkScenarioResult): string {
  const provider = (res.profile_label || res.catalog_owned_by || "").trim();
  const model = (res.model || "").trim();
  if (provider && model) return `${provider} / ${model}`;
  return provider || model || "—";
}

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

function responseFromStreamOnly(res: BenchmarkScenarioResult): boolean {
  const direct = (res.assistant_content || res.assistant_excerpt || "").trim();
  if (direct) return false;
  const stream = res.run_metrics?.bench_diagnostics?.llm_stream;
  return Boolean(stream?.text?.trim() || stream?.reasoning?.trim());
}

function CollapsibleMono({
  text,
  collapsedClass = "max-h-48",
  t,
}: {
  text: string;
  collapsedClass?: string;
  t: (key: string) => string;
}) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > 900 || text.split("\n").length > 14;
  if (!text.trim()) {
    return (
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[11px] text-white/90">
        {t("admin:benchDetailNone")}
      </pre>
    );
  }
  return (
    <div>
      <pre
        className={`overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[11px] text-white/90 ${
          expanded || !long ? "max-h-[32rem]" : collapsedClass
        }`}
      >
        {text}
      </pre>
      {long ? (
        <button
          type="button"
          className="mt-1 text-sky-400 hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t("admin:benchDetailShowLess") : t("admin:benchDetailShowFull")}
        </button>
      ) : null}
    </div>
  );
}

function scenarioHasDiagnostics(res: BenchmarkScenarioResult): boolean {
  return Boolean(
    res.scenario_prompt?.trim() ||
      resolveScenarioResponse(res) ||
      res.agent_run_id ||
      res.error ||
      (res.tool_names?.length ?? 0) > 0
  );
}

function formatInFlightElapsed(inFlight: BenchmarkInFlight): number | null {
  if (typeof inFlight.elapsed_ms === "number" && inFlight.elapsed_ms >= 0) {
    return Math.round(inFlight.elapsed_ms);
  }
  if (!inFlight.started_at) return null;
  const started = Date.parse(inFlight.started_at);
  if (Number.isNaN(started)) return null;
  return Math.max(0, Date.now() - started);
}

function formatInFlightProviderModel(inFlight: BenchmarkInFlight): string {
  const provider = (inFlight.profile_label || inFlight.catalog_owned_by || "").trim();
  const model = (inFlight.model || "").trim();
  if (provider && model) return `${provider} / ${model}`;
  return provider || model || "—";
}

function formatInFlightPromptTokens(inFlight: BenchmarkInFlight): string | null {
  const ppt = inFlight.provider_prompt_tokens;
  if (typeof ppt !== "number" || ppt <= 0) return null;
  const win = inFlight.context_window_tokens;
  if (typeof win === "number" && win > 0) {
    return `${ppt}/${win}`;
  }
  return String(ppt);
}

function formatInFlightToolsColumn(
  inFlight: BenchmarkInFlight,
  t: (key: string) => string
): string {
  const done = inFlight.tool_call_count ?? 0;
  const completedRounds = inFlight.llm_round_count ?? 0;
  const phase = (inFlight.phase || "").trim();
  const currentRound = inFlight.current_llm_round;
  const parts: string[] = [`${done}`];
  if (phase === "llm_generating" && typeof currentRound === "number") {
    parts.push(t("admin:benchInFlightGenRound").replace("{{round}}", String(currentRound)));
  } else {
    parts.push(`${completedRounds} llm`);
  }
  return parts.join(" · ");
}

function formatInFlightActivity(
  inFlight: BenchmarkInFlight,
  t: (key: string) => string
): string {
  const phase = (inFlight.phase || "running").trim();
  const detail = (inFlight.detail || "").trim();
  if (phase === "tool" && detail) {
    return t("admin:benchInFlightTool").replace("{{tool}}", detail);
  }
  if (phase === "llm_generating") {
    const base = detail
      ? t("admin:benchInFlightLlmGeneratingDetail").replace("{{detail}}", detail)
      : t("admin:benchInFlightLlmGenerating");
    const reasoning =
      typeof inFlight.llm_reasoning_chars === "number" && inFlight.llm_reasoning_chars > 0
        ? t("admin:benchInFlightReasoningChars").replace(
            "{{count}}",
            String(inFlight.llm_reasoning_chars)
          )
        : "";
    const text =
      typeof inFlight.llm_text_chars === "number" && inFlight.llm_text_chars > 0
        ? t("admin:benchInFlightTextChars").replace("{{count}}", String(inFlight.llm_text_chars))
        : "";
    const streamHint = reasoning || text ? [reasoning, text].filter(Boolean).join(" · ") : "";
    if (streamHint) return `${base} · ${streamHint}`;
    return base;
  }
  if (phase === "llm") {
    return detail
      ? t("admin:benchInFlightLlmDetail").replace("{{detail}}", detail)
      : t("admin:benchInFlightLlm");
  }
  if (phase === "session") {
    const cat = (inFlight.routed_category || detail || "").trim();
    const n =
      typeof inFlight.forwarded_tool_count === "number"
        ? inFlight.forwarded_tool_count
        : null;
    if (n != null && cat) {
      return t("admin:benchInFlightSessionRoute")
        .replace("{{count}}", String(n))
        .replace("{{category}}", cat);
    }
    if (n != null) {
      return t("admin:benchInFlightSessionTools").replace("{{count}}", String(n));
    }
    return t("admin:benchInFlightSessionGeneric");
  }
  if (phase === "compact") {
    return detail
      ? t("admin:benchInFlightCompact").replace("{{detail}}", detail)
      : t("admin:benchInFlightCompactGeneric");
  }
  if (phase === "project_run") {
    return detail
      ? t("admin:benchInFlightProjectRun").replace("{{status}}", detail)
      : t("admin:benchInFlightProjectRunGeneric");
  }
  if (phase === "starting") return t("admin:benchInFlightStarting");
  return phase;
}

function formatInFlightPreview(inFlight: BenchmarkInFlight): string | null {
  const preview = (inFlight.generation_preview || "").trim();
  if (!preview) return null;
  return preview.length > 140 ? `${preview.slice(0, 140)}…` : preview;
}

function formatResultFailureLine(res: BenchmarkScenarioResult, t: (key: string) => string): string {
  const transport = (res.transport_error || res.error || "").trim();
  const rubric = (res.rubric_failure_reason || "").trim();
  if (transport && rubric) {
    return `${transport} · ${t("admin:benchResultAlsoRubric").replace("{{reason}}", rubric)}`;
  }
  return (res.failure_reason || transport || rubric).trim();
}

function BenchmarkFailuresSummary({
  rows,
  t,
}: {
  rows: BenchExportRow[];
  t: (key: string) => string;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-4 rounded-lg border border-rose-500/25 bg-rose-950/15 p-3">
      <div className="mb-2 text-sm font-medium text-rose-200">
        {t("admin:benchFailuresSummary")} ({rows.length})
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 bg-rose-950/80 text-surface-muted">
            <tr>
              <th className="py-1 pr-2">{t("admin:benchFailuresSummaryColScenario")}</th>
              <th className="py-1 pr-2">{t("admin:benchFailuresSummaryColProfile")}</th>
              <th className="py-1 pr-2">{t("admin:benchFailuresSummaryColTransport")}</th>
              <th className="py-1 pr-2">{t("admin:benchFailuresSummaryColRubric")}</th>
              <th className="py-1 pr-2">{t("admin:benchFailuresSummaryColInsights")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={`${row.scenario_id}-${row.profile_label}-${i}`} className="border-t border-white/5">
                <td className="py-1 pr-2 font-mono align-top">{row.scenario_id}</td>
                <td className="py-1 pr-2 font-mono align-top text-[10px]">
                  {row.profile_label}
                  {row.model ? ` / ${row.model}` : ""}
                </td>
                <td className="py-1 pr-2 align-top text-amber-200/90 max-w-[10rem]">
                  {row.transport_error || "—"}
                </td>
                <td className="py-1 pr-2 align-top text-rose-200/90 max-w-[12rem]">
                  {row.rubric_failure || "—"}
                </td>
                <td className="py-1 pr-2 align-top text-sky-200/80 max-w-[16rem]">
                  {row.insights || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function summarizeToolRounds(
  rounds: Array<{ name?: string; summary?: string | null; rejected?: boolean }>,
): string {
  const counts = new Map<string, number>();
  for (const row of rounds) {
    const name = String(row.name || "").trim();
    if (!name) continue;
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(", ");
}

function BenchmarkScenarioDetail({
  res,
  t,
}: {
  res: BenchmarkScenarioResult;
  t: (key: string) => string;
}) {
  const response = resolveScenarioResponse(res);
  const ctx = res.run_metrics?.context_snapshot;
  const contextWindow =
    ctx && typeof ctx.context_window_tokens === "number"
      ? ctx.context_window_tokens
      : ctx && typeof ctx.budget_tokens === "number"
        ? ctx.budget_tokens
        : null;
  const legacy = !res.scenario_prompt?.trim() && !res.assistant_content?.trim();
  const noToolsForwarded =
    contextWindow === 0 && (res.tool_call_count ?? 0) === 0 && !res.skipped;
  const benchDiag = res.run_metrics?.bench_diagnostics;
  const toolRounds = benchDiag?.tool_rounds ?? [];
  const wsToolSummary = toolRounds.length > 0 ? summarizeToolRounds(toolRounds) : "";
  const toolsDisplay =
    (res.tool_names?.length ?? 0) > 0
      ? res.tool_names!.join(", ")
      : wsToolSummary || t("admin:benchDetailNoTools");
  const traceInvocations = res.run_metrics?.tool_invocations ?? [];
  const runTraceId = res.agent_run_id || benchDiag?.agent_run_id_ws || null;
  const llmStream = benchDiag?.llm_stream;
  const sessionInfo = benchDiag?.session;
  const streamOnly = responseFromStreamOnly(res);

  return (
    <div className="space-y-3 rounded-lg border border-white/10 bg-black/20 p-3 text-xs">
      {noToolsForwarded ? (
        <p className="text-amber-400/90">{t("admin:benchDetailNoToolsForwarded")}</p>
      ) : null}
      {legacy && response ? (
        <p className="text-amber-400/90">{t("admin:benchDetailLegacyHint")}</p>
      ) : null}
      {legacy && !response ? (
        <p className="text-surface-muted">{t("admin:benchDetailLegacyHint")}</p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 font-medium text-surface-muted">{t("admin:benchDetailPrompt")}</div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[11px] text-white/90">
            {res.scenario_prompt?.trim() || t("admin:benchDetailNone")}
          </pre>
        </div>
        <div>
          <div className="mb-1 font-medium text-surface-muted">
            {t("admin:benchDetailResponse")}
            {res.assistant_content_truncated ? (
              <span className="ml-2 font-normal text-amber-400/80">
                ({t("admin:benchDetailTruncated")})
              </span>
            ) : null}
            {streamOnly ? (
              <span className="ml-2 font-normal text-amber-400/80">
                ({t("admin:benchDetailResponseFromStream")})
              </span>
            ) : null}
          </div>
          <CollapsibleMono text={response || ""} t={t} />
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-surface-muted">
        <span>
          {t("admin:benchDetailTools")}:{" "}
          <span className="font-mono text-white/80">{toolsDisplay}</span>
          {(res.tool_names?.length ?? 0) === 0 && toolRounds.length > 0 ? (
            <span className="ml-1 text-amber-400/80">({t("admin:benchDetailToolsFromWs")})</span>
          ) : null}
        </span>
        {res.run_metrics?.capture_mode ? (
          <span>
            {t("admin:benchDetailCaptureMode")}:{" "}
            <span className="font-mono text-white/80">{res.run_metrics.capture_mode}</span>
          </span>
        ) : null}
        {contextWindow != null ? (
          <span>
            {t("admin:benchDetailContextWindow")}:{" "}
            <span className="font-mono text-white/80">{contextWindow}</span>
          </span>
        ) : null}
        {res.run_metrics?.provider_cache?.cache_prompt_disabled === true ? (
          <span>{t("admin:benchDetailProviderCacheOff")}</span>
        ) : null}
        {typeof res.run_metrics?.provider_cached_prompt_tokens === "number" ? (
          <span>
            {t("admin:benchDetailProviderCacheHit")}:{" "}
            <span className="font-mono text-white/80">
              {res.run_metrics.provider_cached_prompt_tokens}
            </span>
          </span>
        ) : null}
        {sessionInfo?.forwarded_tool_count != null ? (
          <span>
            {t("admin:benchDetailForwardedTools")}:{" "}
            <span className="font-mono text-white/80">
              {sessionInfo.forwarded_tool_count}
              {sessionInfo.routed_category ? ` (${sessionInfo.routed_category})` : ""}
            </span>
          </span>
        ) : null}
      </div>
      {sessionInfo?.forwarded_tools?.length ? (
        <div>
          <div className="mb-1 font-medium text-surface-muted">{t("admin:benchDetailToolCatalog")}</div>
          <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[10px] text-white/80">
            {sessionInfo.forwarded_tools.join(", ")}
          </pre>
        </div>
      ) : null}
      {llmStream?.reasoning || llmStream?.text ? (
        <div className="space-y-2">
          <div className="font-medium text-surface-muted">{t("admin:benchDetailLlmStream")}</div>
          {llmStream.reasoning ? (
            <div>
              <div className="mb-1 text-[10px] text-surface-muted">
                {t("admin:benchDetailLlmReasoning")}
                {typeof llmStream.reasoning_chars === "number"
                  ? ` · ${llmStream.reasoning_chars} chars`
                  : ""}
                {llmStream.reasoning_truncated ? ` · ${t("admin:benchDetailTruncated")}` : ""}
              </div>
              <CollapsibleMono text={llmStream.reasoning} collapsedClass="max-h-36" t={t} />
            </div>
          ) : null}
          {llmStream.text ? (
            <div>
              <div className="mb-1 text-[10px] text-surface-muted">
                {t("admin:benchDetailLlmText")}
                {typeof llmStream.text_chars === "number" ? ` · ${llmStream.text_chars} chars` : ""}
                {llmStream.text_truncated ? ` · ${t("admin:benchDetailTruncated")}` : ""}
              </div>
              <CollapsibleMono text={llmStream.text} collapsedClass="max-h-36" t={t} />
            </div>
          ) : null}
        </div>
      ) : null}
      {(res.transport_error || res.error) ? (
        <div className="rounded border border-amber-500/25 bg-amber-950/20 p-2">
          <div className="font-medium text-amber-300">{t("admin:benchDetailTransportError")}</div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-amber-100/90">
            {res.transport_error || res.error}
          </pre>
          {res.run_metrics?.http_status != null ? (
            <p className="mt-1 text-surface-muted">
              HTTP {res.run_metrics.http_status}
            </p>
          ) : null}
        </div>
      ) : null}
      {res.rubric_failure_reason ? (
        <div className="rounded border border-red-500/30 bg-red-950/30 p-2">
          <div className="font-medium text-red-300">{t("admin:benchDetailRubricFailure")}</div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-red-200/90">
            {res.rubric_failure_reason}
          </pre>
        </div>
      ) : null}
      {!res.rubric_failure_reason && res.failure_reason && !(res.transport_error || res.error) ? (
        <div className="rounded border border-red-500/30 bg-red-950/30 p-2">
          <div className="font-medium text-red-300">{t("admin:benchDetailFailure")}</div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-red-200/90">
            {res.failure_reason}
          </pre>
        </div>
      ) : null}
      {(benchDiag?.insights?.length ?? 0) > 0 ? (
        <div className="rounded border border-sky-500/25 bg-sky-950/25 p-2">
          <div className="font-medium text-sky-300">{t("admin:benchDetailInsights")}</div>
          <ul className="mt-1 list-inside list-disc text-[11px] text-sky-100/90">
            {benchDiag!.insights!.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {toolRounds.length > 0 ? (
        <div>
          <div className="mb-1 font-medium text-surface-muted">{t("admin:benchDetailToolRounds")}</div>
          <div className="max-h-48 overflow-auto rounded bg-black/30">
            <table className="w-full font-mono text-[10px] text-white/85">
              <thead className="sticky top-0 bg-black/60 text-surface-muted">
                <tr>
                  <th className="px-2 py-1 text-left">{t("admin:benchDetailToolRoundCol")}</th>
                  <th className="px-2 py-1 text-left">{t("admin:benchDetailToolNameCol")}</th>
                  <th className="px-2 py-1 text-left">{t("admin:benchDetailToolArgsCol")}</th>
                  <th className="px-2 py-1 text-left">{t("admin:benchDetailToolResultCol")}</th>
                </tr>
              </thead>
              <tbody>
                {toolRounds.map((row, i) => {
                  const args = String(row.summary || "").trim() || t("admin:benchDetailNone");
                  const rejected = row.rejected === true;
                  let result = t("admin:benchDetailNone");
                  if (rejected) result = t("admin:benchDetailToolRejected");
                  else if (row.ok === false) result = String(row.error || t("admin:benchDetailToolFailed"));
                  else if (row.ok === true) result = t("admin:benchDetailToolOk");
                  return (
                    <tr key={i} className="border-t border-white/5">
                      <td className="px-2 py-1">{row.round ?? "—"}</td>
                      <td className="px-2 py-1">{row.name || "—"}</td>
                      <td className="max-w-[12rem] truncate px-2 py-1" title={args}>
                        {args}
                      </td>
                      <td className="max-w-[14rem] truncate px-2 py-1 text-amber-200/90" title={result}>
                        {result}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {traceInvocations.length > 0 ? (
        <div>
          <div className="mb-1 font-medium text-surface-muted">{t("admin:benchDetailToolTrace")}</div>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[10px] text-white/80">
            {traceInvocations
              .map((inv) => {
                const name = String(inv.tool_name || "?");
                const args = inv.args_preview ? ` args=${inv.args_preview}` : "";
                const ok =
                  inv.ok === true ? " ok" : inv.ok === false ? " FAIL" : "";
                const err = inv.result_error ? ` err=${inv.result_error}` : "";
                return `${name}${args}${ok}${err}`;
              })
              .join("\n")}
          </pre>
        </div>
      ) : null}
      {res.run_metrics?.bench_diagnostics?.ws_errors?.length ? (
        <div className="rounded border border-amber-500/20 bg-amber-950/20 p-2">
          <div className="font-medium text-amber-300">{t("admin:benchDetailWsErrors")}</div>
          <ul className="mt-1 list-inside list-disc font-mono text-[11px] text-amber-100/90">
            {res.run_metrics.bench_diagnostics.ws_errors.map((row, i) => (
              <li key={i}>
                {row.type || "error"}
                {row.http_status != null ? ` · HTTP ${row.http_status}` : ""}
                {row.detail ? `: ${String(row.detail)}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {(res.run_metrics?.bench_diagnostics?.timeline_tail?.length ?? 0) > 0 ? (
        <div>
          <div className="mb-1 font-medium text-surface-muted">{t("admin:benchDetailTimeline")}</div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 font-mono text-[10px] text-white/80">
            {res.run_metrics!.bench_diagnostics!.timeline_tail!
              .map((ev) => {
                const typ = String(ev.type || "?");
                const tool = ev.tool ? ` tool=${ev.tool}` : "";
                const round = ev.round != null ? ` round=${ev.round}` : "";
                const phase = ev.phase ? ` phase=${ev.phase}` : "";
                const summary = ev.summary ? ` args=${String(ev.summary)}` : "";
                const ok =
                  ev.ok === false
                    ? " FAIL"
                    : ev.ok === true
                      ? " ok"
                      : "";
                const err = ev.error ? ` err=${String(ev.error)}` : "";
                return `${typ}${tool}${round}${phase}${summary}${ok}${err}`;
              })
              .join("\n")}
          </pre>
        </div>
      ) : null}
      {res.run_metrics?.bench_diagnostics?.event_counts ? (
        <p className="text-surface-muted">
          {t("admin:benchDetailEventCounts")}:{" "}
          <span className="font-mono text-white/75">
            llm={res.run_metrics.bench_diagnostics.event_counts.llm_round_count ?? 0},{" "}
            tool_start={res.run_metrics.bench_diagnostics.event_counts.tool_start_count ?? 0},{" "}
            tool_done={res.run_metrics.bench_diagnostics.event_counts.tool_done_count ?? 0}
          </span>
        </p>
      ) : null}
      {runTraceId ? (
        <Link
          to={`/app/admin/run-traces?run=${encodeURIComponent(runTraceId)}`}
          className="inline-block text-sky-400 hover:underline"
        >
          {t("admin:benchDetailRunTrace")} · {runTraceId.slice(0, 8)}…
        </Link>
      ) : null}
    </div>
  );
}

export function AdminBenchmarks() {
  const { t } = useTranslation(["admin"]);
  const auth = useAuth();
  const { user: authUser } = auth;
  const [tab, setTab] = useState<"run" | "history">("run");
  const [suites, setSuites] = useState<BenchmarkSuite[]>([]);
  const [catalogFixtures, setCatalogFixtures] = useState<BenchmarkFixture[]>([]);
  const [tenantUsers, setTenantUsers] = useState<AdminUserRow[]>([]);
  const [runAsUserId, setRunAsUserId] = useState("");
  const [friendUserId, setFriendUserId] = useState("");
  const [readiness, setReadiness] = useState<BenchmarkRunReadiness | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [suite, setSuite] = useState("smoke");
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<Set<string>>(new Set());
  const [extraFixtureIds, setExtraFixtureIds] = useState<Set<string>>(new Set());
  const [expandedScenarioId, setExpandedScenarioId] = useState<string | null>(null);
  const [llmProviders, setLlmProviders] = useState<BenchmarkLlmProvider[]>([]);
  const [selectedProviderIds, setSelectedProviderIds] = useState<Set<string>>(new Set());
  const [modelByProviderId, setModelByProviderId] = useState<Map<string, string>>(new Map());
  const [catalogRows, setCatalogRows] = useState<ModelRow[]>([]);
  const [catalogAgentlayer, setCatalogAgentlayer] = useState<ModelCatalogAgentlayer | null>(null);
  const [runs, setRuns] = useState<BenchmarkRun[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BenchmarkRun | null>(null);
  const [expandedResultKey, setExpandedResultKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [cancellingRunId, setCancellingRunId] = useState<string | null>(null);
  const [scenarioTimeoutSec, setScenarioTimeoutSec] = useState("");
  const [maxToolRoundsOverride, setMaxToolRoundsOverride] = useState("");
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [deleteRunTarget, setDeleteRunTarget] = useState<BenchmarkRun | null>(null);
  const scenariosInitialized = useRef(false);

  const suiteDetail = useMemo(
    () => suites.find((s) => s.id === suite) ?? null,
    [suites, suite]
  );

  const autoFixtures = useMemo(() => {
    if (!suiteDetail) return new Set<string>();
    return autoFixtureIds(suiteDetail, selectedScenarioIds);
  }, [suiteDetail, selectedScenarioIds]);

  const benchProviders = useMemo(() => llmProviders.filter((p) => Boolean(p.base_url?.trim())), [llmProviders]);

  const showFriendPicker = autoFixtures.has("friend_pair");

  const friendCandidates = useMemo(
    () => tenantUsers.filter((u) => u.id !== runAsUserId && u.role === "user"),
    [tenantUsers, runAsUserId]
  );

  const runAsUser = useMemo(
    () => tenantUsers.find((u) => u.id === runAsUserId) ?? null,
    [tenantUsers, runAsUserId]
  );

  const scenarioSecretWarning = useCallback(
    (sc: BenchmarkScenario): string | null => {
      const needsGmail = sc.requires.includes("gmail_secret");
      const needsSsc = sc.requires.includes("ssc_secret");
      if (!needsGmail && !needsSsc) return null;
      if (!readiness) return null;
      if (!readiness.secrets_enabled) return t("admin:benchSecretsDisabled");
      if (needsGmail && !readiness.secrets.gmail) return t("admin:benchSkipGmail");
      if (needsSsc && !readiness.secrets.ssc_api_key) return t("admin:benchSkipSsc");
      return null;
    },
    [readiness, t]
  );

  const activeFixtures = useMemo(() => {
    const ids = new Set(autoFixtures);
    extraFixtureIds.forEach((id) => ids.add(id));
    const byId = new Map((suiteDetail?.fixtures ?? catalogFixtures).map((f) => [f.id, f]));
    return [...ids].map((id) => byId.get(id)).filter(Boolean) as BenchmarkFixture[];
  }, [autoFixtures, extraFixtureIds, suiteDetail, catalogFixtures]);

  const syncScenariosForSuite = useCallback((nextSuite: BenchmarkSuite | null) => {
    if (!nextSuite?.scenarios?.length) {
      setSelectedScenarioIds(new Set());
      return;
    }
    setSelectedScenarioIds(new Set(nextSuite.scenarios.map((sc) => sc.id)));
    setExtraFixtureIds(new Set());
    setExpandedScenarioId(null);
  }, []);

  const loadMeta = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, providers, catalog, users, modelCatalog] = await Promise.all([
        fetchBenchmarkSuites(auth),
        fetchBenchmarkLlmProviders(auth),
        fetchBenchmarkCatalog(auth),
        fetchAdminUsers(auth),
        fetchModelCatalog(),
      ]);
      setCatalogRows(modelCatalog.rows);
      setCatalogAgentlayer(modelCatalog.agentlayer);
      setSuites(s);
      setCatalogFixtures(catalog.fixtures);
      setLlmProviders(providers);
      setTenantUsers(users);
      setRunAsUserId((prev) => {
        if (prev && users.some((u) => u.id === prev)) return prev;
        if (authUser?.id && users.some((u) => u.id === authUser.id)) return authUser.id;
        return users[0]?.id ?? "";
      });
      const usable = providers.filter((p) => p.base_url?.trim());
      setSelectedProviderIds((prev) => {
        if (prev.size) {
          const next = new Set([...prev].filter((id) => usable.some((p) => p.catalog_owned_by === id)));
          return next.size ? next : new Set(usable.map((p) => p.catalog_owned_by));
        }
        return new Set(usable.map((p) => p.catalog_owned_by));
      });
      setModelByProviderId((prev) => {
        const next = new Map(prev);
        usable.forEach((p) => {
          next.set(
            p.catalog_owned_by,
            resolveInitialProviderModel(p, modelCatalog.rows, prev.get(p.catalog_owned_by))
          );
        });
        return next;
      });
      if (s.length && !s.some((x) => x.id === suite)) {
        setSuite(s[0].id);
      }
      if (!scenariosInitialized.current && s.length) {
        scenariosInitialized.current = true;
        const detail = s.find((x) => x.id === suite) ?? s[0];
        syncScenariosForSuite(detail ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth, authUser?.id, suite, syncScenariosForSuite, t]);

  useEffect(() => {
    if (!runAsUserId || tab !== "run") {
      setReadiness(null);
      return;
    }
    let cancelled = false;
    setReadinessLoading(true);
    void (async () => {
      try {
        const row = await fetchBenchmarkRunReadiness(auth, runAsUserId);
        if (!cancelled) setReadiness(row);
      } catch {
        if (!cancelled) setReadiness(null);
      } finally {
        if (!cancelled) setReadinessLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, runAsUserId, tab]);

  useEffect(() => {
    if (!showFriendPicker) {
      setFriendUserId("");
      return;
    }
    if (friendUserId && friendCandidates.some((u) => u.id === friendUserId)) return;
    setFriendUserId(friendCandidates[0]?.id ?? "");
  }, [showFriendPicker, friendCandidates, friendUserId]);

  const onSuiteChange = (nextId: string) => {
    setSuite(nextId);
    syncScenariosForSuite(suites.find((s) => s.id === nextId) ?? null);
  };

  const toggleScenario = (id: string) => {
    setSelectedScenarioIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllScenarios = () => {
    if (!suiteDetail?.scenarios) return;
    setSelectedScenarioIds(new Set(suiteDetail.scenarios.map((sc) => sc.id)));
  };

  const toggleExtraFixture = (id: string) => {
    setExtraFixtureIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const loadRuns = useCallback(async () => {
    try {
      const list = await fetchBenchmarkRuns(auth);
      setRuns(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchLoadFailed"));
    }
  }, [auth, t]);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    if (tab === "history") void loadRuns();
  }, [tab, loadRuns]);

  useEffect(() => {
    setExpandedResultKey(null);
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void (async () => {
      try {
        const d = await fetchBenchmarkRun(auth, selectedId);
        setDetail(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("admin:benchLoadFailed"));
      }
    })();
  }, [auth, selectedId, t]);

  const loadSelectedDetail = useCallback(async () => {
    if (!selectedId) return;
    try {
      const d = await fetchBenchmarkRun(auth, selectedId);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchLoadFailed"));
    }
  }, [auth, selectedId, t]);

  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedId) ?? null,
    [runs, selectedId]
  );

  const pollRunning = useMemo(
    () => runs.some((r) => r.status === "queued" || r.status === "running"),
    [runs]
  );

  const shouldPollDetail = useMemo(
    () =>
      tab === "history" &&
      Boolean(selectedId) &&
      (pollRunning ||
        selectedRun?.status === "queued" ||
        selectedRun?.status === "running"),
    [tab, selectedId, pollRunning, selectedRun]
  );

  const wasPollingRef = useRef(false);

  useEffect(() => {
    if (!shouldPollDetail) return;
    void loadRuns();
    void loadSelectedDetail();
    const id = window.setInterval(() => {
      void (async () => {
        await loadRuns();
        await loadSelectedDetail();
      })();
    }, 3000);
    return () => window.clearInterval(id);
  }, [shouldPollDetail, loadRuns, loadSelectedDetail]);

  useEffect(() => {
    if (wasPollingRef.current && !shouldPollDetail && selectedId) {
      void loadSelectedDetail();
      void loadRuns();
    }
    wasPollingRef.current = shouldPollDetail;
  }, [shouldPollDetail, selectedId, loadSelectedDetail, loadRuns]);

  const toggleProvider = (id: string) => {
    setSelectedProviderIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else {
        next.add(id);
        const p = benchProviders.find((row) => row.catalog_owned_by === id);
        if (p) {
          setModelByProviderId((models) => {
            const current = (models.get(id) ?? defaultProviderModel(p)).trim();
            if (current) return models;
            const resolved = resolveInitialProviderModel(p, catalogRows, undefined);
            if (!resolved) return models;
            const nextModels = new Map(models);
            nextModels.set(id, resolved);
            return nextModels;
          });
        }
      }
      return next;
    });
  };

  const selectAllProviders = () => {
    setSelectedProviderIds(new Set(benchProviders.map((p) => p.catalog_owned_by)));
  };

  const setProviderModel = (id: string, model: string) => {
    setModelByProviderId((prev) => {
      const next = new Map(prev);
      next.set(id, model);
      return next;
    });
  };

  const onStart = async () => {
    setStarting(true);
    setError(null);
    const profiles = buildProfilesFromSelection(
      benchProviders,
      selectedProviderIds,
      modelByProviderId
    );
    if (!profiles.length) {
      setError(
        selectedProviderIds.size
          ? t("admin:benchNeedModel")
          : t("admin:benchNeedProfile")
      );
      setStarting(false);
      return;
    }
    if (!selectedScenarioIds.size) {
      setError(t("admin:benchNeedScenario"));
      setStarting(false);
      return;
    }
    const allIds = suiteDetail?.scenarios?.map((sc) => sc.id) ?? [];
    const scenarios =
      selectedScenarioIds.size === allIds.length ? undefined : [...selectedScenarioIds];
    const extras = [...extraFixtureIds].filter((id) => !autoFixtures.has(id));
    const timeoutRaw = scenarioTimeoutSec.trim();
    const maxRoundsRaw = maxToolRoundsOverride.trim();
    const parsedTimeout = timeoutRaw ? Number(timeoutRaw) : NaN;
    const parsedMaxRounds = maxRoundsRaw ? Number(maxRoundsRaw) : NaN;
    if (timeoutRaw && (!Number.isFinite(parsedTimeout) || parsedTimeout < 30)) {
      setError(t("admin:benchTimeoutInvalid"));
      setStarting(false);
      return;
    }
    if (maxRoundsRaw && (!Number.isFinite(parsedMaxRounds) || parsedMaxRounds < 1)) {
      setError(t("admin:benchMaxRoundsInvalid"));
      setStarting(false);
      return;
    }
    try {
      const run = await startBenchmarkRun(auth, {
        suite,
        profiles,
        scenarios,
        fixtures: extras.length ? extras : undefined,
        run_as_user_id: runAsUserId || undefined,
        friend_user_id: showFriendPicker && friendUserId ? friendUserId : undefined,
        scenario_timeout_sec: timeoutRaw ? parsedTimeout : undefined,
        max_tool_rounds_override: maxRoundsRaw ? Math.floor(parsedMaxRounds) : undefined,
      });
      setTab("history");
      setSelectedId(run.id);
      await loadRuns();
      try {
        setDetail(await fetchBenchmarkRun(auth, run.id));
      } catch {
        /* detail poll will retry */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchStartFailed"));
    } finally {
      setStarting(false);
    }
  };

  const requestDeleteRun = (run: BenchmarkRun) => {
    if (run.status === "queued" || run.status === "running") {
      setError(t("admin:benchDeleteRunActive"));
      return;
    }
    setError(null);
    setDeleteRunTarget(run);
  };

  const onCancelRun = async (run: BenchmarkRun) => {
    if (run.status !== "queued" && run.status !== "running") return;
    setCancellingRunId(run.id);
    setError(null);
    try {
      await cancelBenchmarkRun(auth, run.id);
      await loadRuns();
      if (selectedId === run.id) {
        try {
          setDetail(await fetchBenchmarkRun(auth, run.id));
        } catch {
          /* poll will retry */
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchCancelFailed"));
    } finally {
      setCancellingRunId(null);
    }
  };

  const confirmDeleteRun = async () => {
    if (!deleteRunTarget) return;
    const run = deleteRunTarget;
    setDeletingRunId(run.id);
    setError(null);
    try {
      await deleteBenchmarkRun(auth, run.id);
      setDeleteRunTarget(null);
      if (selectedId === run.id) {
        setSelectedId(null);
        setDetail(null);
      }
      await loadRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("admin:benchDeleteRunFailed"));
    } finally {
      setDeletingRunId(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden p-4">
      <div className="shrink-0">
        <h1 className="text-lg font-semibold text-white">{t("admin:benchTitle")}</h1>
        <p className="mt-1 text-sm text-surface-muted">{t("admin:benchSubtitle")}</p>
        <p className="mt-2 text-xs text-surface-muted">
          {t("admin:benchDbProfilesHint")}{" "}
          <Link to="/admin/interfaces/llm" className="text-sky-400/90 hover:underline">
            {t("admin:llmRouting")}
          </Link>
          . {t("admin:benchRunIdentityHint")}
        </p>
      </div>

      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={() => setTab("run")}
          className={`rounded-lg px-3 py-1.5 text-sm ${
            tab === "run" ? "bg-white/15 text-white" : "text-surface-muted hover:bg-white/5"
          }`}
        >
          {t("admin:benchTabRun")}
        </button>
        <button
          type="button"
          onClick={() => setTab("history")}
          className={`rounded-lg px-3 py-1.5 text-sm ${
            tab === "history" ? "bg-white/15 text-white" : "text-surface-muted hover:bg-white/5"
          }`}
        >
          {t("admin:benchTabHistory")}
        </button>
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {loading && tab === "run" ? (
        <p className="text-sm text-surface-muted">{t("admin:loading")}</p>
      ) : null}

      {tab === "run" && !loading ? (
        <div className="min-h-0 flex-1 overflow-y-auto space-y-4">
          <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
            <h2 className="text-sm font-medium text-white">{t("admin:benchRunIdentity")}</h2>
            <p className="mt-1 text-xs text-surface-muted">{t("admin:benchRunIdentityDesc")}</p>
            <label className="mt-3 block text-xs text-surface-muted">{t("admin:benchRunAs")}</label>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <select
                value={runAsUserId}
                onChange={(e) => setRunAsUserId(e.target.value)}
                className="min-w-[16rem] flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
              >
                {tenantUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {userOptionLabel(u)}
                  </option>
                ))}
              </select>
              <Link
                to="/admin/users"
                className="text-xs text-sky-400 hover:underline"
              >
                {t("admin:benchManageUsers")}
              </Link>
            </div>
            {showFriendPicker ? (
              <>
                <label className="mt-3 block text-xs text-surface-muted">
                  {t("admin:benchFriendUser")}
                </label>
                <select
                  value={friendUserId}
                  onChange={(e) => setFriendUserId(e.target.value)}
                  className="mt-1 w-full max-w-md rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
                >
                  {friendCandidates.length === 0 ? (
                    <option value="">{t("admin:benchFriendUserEmpty")}</option>
                  ) : (
                    friendCandidates.map((u) => (
                      <option key={u.id} value={u.id}>
                        {userOptionLabel(u)}
                      </option>
                    ))
                  )}
                </select>
                <p className="mt-1 text-[11px] text-surface-muted">{t("admin:benchFriendUserHint")}</p>
              </>
            ) : null}
            <div className="mt-4 border-t border-white/5 pt-3">
              <p className="text-xs font-medium text-white">{t("admin:benchSecretReadiness")}</p>
              {readinessLoading ? (
                <p className="mt-2 text-xs text-surface-muted">{t("admin:loading")}</p>
              ) : readiness ? (
                <ul className="mt-2 space-y-1 text-xs">
                  <li className={readiness.secrets.gmail ? "text-emerald-300/90" : "text-amber-400/90"}>
                    Gmail: {readiness.secrets.gmail ? t("admin:benchSecretOk") : t("admin:benchSecretMissing")}
                  </li>
                  <li
                    className={
                      readiness.secrets.ssc_api_key ? "text-emerald-300/90" : "text-amber-400/90"
                    }
                  >
                    SSC API key:{" "}
                    {readiness.secrets.ssc_api_key
                      ? t("admin:benchSecretOk")
                      : t("admin:benchSecretMissing")}
                  </li>
                  {!readiness.secrets_enabled ? (
                    <li className="text-amber-400/90">{t("admin:benchSecretsDisabled")}</li>
                  ) : null}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-surface-muted">{t("admin:benchReadinessUnavailable")}</p>
              )}
              <p className="mt-2 text-[11px] text-surface-muted">
                {t("admin:benchSecretsAutoHint")}
              </p>
              <p className="mt-2 text-[11px] text-surface-muted">
                {t("admin:benchSecretsManageHint")}{" "}
                <Link to="/settings/connections" className="text-sky-400/90 hover:underline">
                  {t("admin:benchSecretsSettingsLink")}
                </Link>
              </p>
            </div>
          </section>

          <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-medium text-white">{t("admin:benchProfiles")}</h2>
                <p className="text-xs text-surface-muted">{t("admin:benchDbProfilesSelectHint")}</p>
              </div>
              {benchProviders.length ? (
                <button
                  type="button"
                  onClick={selectAllProviders}
                  className="text-xs text-sky-400 hover:underline"
                >
                  {t("admin:benchSelectAllEndpoints")}
                </button>
              ) : null}
            </div>

            {benchProviders.length ? (
              <div className="mt-3 space-y-2">
                {benchProviders.map((p) => {
                  const checked = selectedProviderIds.has(p.catalog_owned_by);
                  const model = modelByProviderId.get(p.catalog_owned_by) ?? defaultProviderModel(p);
                  const catalogModels = catalogModelIdsForProvider(catalogRows, p.catalog_owned_by);
                  const providerUnreachable = isProviderCatalogUnreachable(
                    p.catalog_owned_by,
                    catalogAgentlayer
                  );
                  const providerDetail =
                    catalogAgentlayer?.[p.catalog_owned_by]?.detail?.trim() ?? "";
                  return (
                    <div
                      key={p.catalog_owned_by}
                      className={`rounded-lg border p-3 ${
                        checked ? "border-sky-500/30 bg-sky-950/20" : "border-white/10 bg-black/20"
                      }`}
                    >
                      <label className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleProvider(p.catalog_owned_by)}
                          className="mt-1"
                        />
                        <div className="min-w-0 flex-1 text-xs">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-white">
                              {p.label || p.base_url}
                            </span>
                            <span className="font-mono text-surface-muted">{p.catalog_owned_by}</span>
                            {p.source === "env" ? (
                              <span className="rounded bg-emerald-950/40 px-1.5 py-0.5 text-[10px] text-emerald-200">
                                .env
                              </span>
                            ) : null}
                            {p.endpoint_id != null ? (
                              <span className="font-mono text-surface-muted">db id={p.endpoint_id}</span>
                            ) : null}
                          </div>
                          <p className="mt-1 text-surface-muted">{p.base_url}</p>
                        </div>
                      </label>
                      {checked ? (
                        <label className="mt-3 block text-xs">
                          <span className="text-surface-muted">{t("admin:benchModel")}</span>
                          {catalogModels.length > 0 ? (
                            <select
                              value={model}
                              onChange={(e) => setProviderModel(p.catalog_owned_by, e.target.value)}
                              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-sm font-mono text-white"
                            >
                              {!catalogModels.includes(model) && model ? (
                                <option value={model}>{model}</option>
                              ) : null}
                              {catalogModels.map((id) => (
                                <option key={id} value={id}>
                                  {id}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <>
                              <input
                                value={model}
                                onChange={(e) => setProviderModel(p.catalog_owned_by, e.target.value)}
                                className="mt-1 w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-sm font-mono"
                                placeholder={defaultProviderModel(p) || t("admin:benchModelMissing")}
                              />
                              <p className="mt-1 text-surface-muted">
                                {providerUnreachable
                                  ? t("admin:benchModelCatalogUnreachable", {
                                      detail: providerDetail || p.base_url,
                                    })
                                  : t("admin:benchModelCatalogEmpty")}
                              </p>
                            </>
                          )}
                        </label>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-xs text-amber-200/90">
                {t("admin:benchDbProfilesEmpty")}{" "}
                <Link to="/admin/interfaces/llm" className="text-sky-400 hover:underline">
                  {t("admin:llmRouting")}
                </Link>
              </p>
            )}
          </section>

          <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
            <label className="block text-xs text-surface-muted">{t("admin:benchSuite")}</label>
            <select
              value={suite}
              onChange={(e) => onSuiteChange(e.target.value)}
              className="mt-1 w-full max-w-md rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
            >
              {suites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            {suiteDetail?.description ? (
              <p className="mt-2 text-xs text-surface-muted">{suiteDetail.description}</p>
            ) : null}
          </section>

          <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-medium text-white">{t("admin:benchScenarios")}</h2>
                <p className="text-xs text-surface-muted">{t("admin:benchScenariosHint")}</p>
              </div>
              <button
                type="button"
                onClick={selectAllScenarios}
                className="text-xs text-sky-400 hover:underline"
              >
                {t("admin:benchSelectAllScenarios")}
              </button>
            </div>
            {activeFixtures.length > 0 ? (
              <p className="mt-2 text-[11px] text-surface-muted">
                {t("admin:benchAutoSetup")}:{" "}
                {activeFixtures.map((fx) => fx.title).join(" · ")}
              </p>
            ) : null}
            <div className="mt-3 space-y-2">
              {(suiteDetail?.scenarios ?? []).map((sc: BenchmarkScenario) => {
                const checked = selectedScenarioIds.has(sc.id);
                const expanded = expandedScenarioId === sc.id;
                return (
                  <div
                    key={sc.id}
                    className={`rounded-lg border p-3 ${
                      checked ? "border-sky-500/30 bg-sky-950/20" : "border-white/10 bg-black/20"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleScenario(sc.id)}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-sky-300/90">{sc.id}</span>
                          <span className="text-sm text-white">{sc.title}</span>
                          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-surface-muted">
                            {t("admin:benchTier", { n: sc.tier })}
                          </span>
                          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-surface-muted">
                            {sc.agent_id}
                          </span>
                          {sc.execution && sc.execution !== "chat" ? (
                            <span className="rounded bg-violet-950/50 px-1.5 py-0.5 text-[10px] text-violet-200">
                              {sc.execution}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-surface-muted">{sc.summary}</p>
                        {sc.expected_tools.length ? (
                          <p className="mt-1 text-[11px] text-surface-muted">
                            {t("admin:benchExpectedTools")}:{" "}
                            {sc.expected_tools.join(", ")}
                          </p>
                        ) : null}
                        {sc.requires.length ? (
                          <p className="mt-0.5 text-[11px] text-surface-muted">
                            {t("admin:benchFixturesRequired")}: {sc.requires.join(", ")}
                          </p>
                        ) : null}
                        {(() => {
                          const secretWarn = scenarioSecretWarning(sc);
                          if (secretWarn) {
                            return (
                              <p className="mt-0.5 text-[11px] text-amber-400/90">
                                {t("admin:benchWillSkip")}: {secretWarn}
                              </p>
                            );
                          }
                          if (sc.skip_without_env) {
                            return (
                              <p className="mt-0.5 text-[11px] text-amber-400/90">
                                {t("admin:benchEnvSkip")}: {sc.skip_without_env}
                              </p>
                            );
                          }
                          return null;
                        })()}
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedScenarioId(expanded ? null : sc.id)
                          }
                          className="mt-1 text-[11px] text-sky-400 hover:underline"
                        >
                          {expanded ? t("admin:benchHidePrompt") : t("admin:benchShowPrompt")}
                        </button>
                        {expanded ? (
                          <div className="mt-2 space-y-1 rounded border border-white/5 bg-black/30 p-2 text-[11px]">
                            <p className="text-surface-muted">{t("admin:benchPrompt")}</p>
                            <p className="whitespace-pre-wrap text-white/90">{sc.prompt}</p>
                            <p className="text-surface-muted">{t("admin:benchRubric")}: {sc.rubric}</p>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-xl border border-surface-border bg-surface-raised/40 p-4 space-y-3">
            <h3 className="text-xs font-medium uppercase text-surface-muted">
              {t("admin:benchAdvancedOptions")}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="text-surface-muted">{t("admin:benchScenarioTimeout")}</span>
                <input
                  type="number"
                  min={30}
                  step={30}
                  value={scenarioTimeoutSec}
                  onChange={(e) => setScenarioTimeoutSec(e.target.value)}
                  placeholder={t("admin:benchScenarioTimeoutPlaceholder")}
                  className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                />
                <span className="mt-1 block text-[11px] text-surface-muted">
                  {t("admin:benchScenarioTimeoutHint")}
                </span>
              </label>
              <label className="block text-sm">
                <span className="text-surface-muted">{t("admin:benchMaxToolRounds")}</span>
                <input
                  type="number"
                  min={1}
                  max={512}
                  value={maxToolRoundsOverride}
                  onChange={(e) => setMaxToolRoundsOverride(e.target.value)}
                  placeholder={t("admin:benchMaxToolRoundsPlaceholder")}
                  className="mt-1 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                />
                <span className="mt-1 block text-[11px] text-surface-muted">
                  {t("admin:benchMaxToolRoundsHint")}
                </span>
              </label>
            </div>
            <button
              type="button"
              disabled={starting || !runAsUserId}
              onClick={() => void onStart()}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {starting ? t("admin:benchStarting") : t("admin:benchStart")}
            </button>
            <p className="text-xs text-surface-muted">
              {t("admin:benchRunNote", {
                user: runAsUser ? userOptionLabel(runAsUser) : runAsUserId || "—",
              })}
            </p>
          </section>
        </div>
      ) : null}

      {tab === "history" ? (
        <div className="flex min-h-0 flex-1 gap-4 overflow-hidden">
          <div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border border-surface-border bg-surface-raised/40">
            <div className="flex items-center justify-between border-b border-white/5 px-3 py-2">
              <span className="text-xs font-medium uppercase text-surface-muted">
                {t("admin:benchHistory")}
              </span>
              <button
                type="button"
                onClick={() => void loadRuns()}
                className="text-xs text-sky-400"
              >
                {t("admin:agentTracesRefresh")}
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {runs.length === 0 ? (
                <p className="p-3 text-xs text-surface-muted">{t("admin:benchNone")}</p>
              ) : (
                runs.map((r) => (
                  <div
                    key={r.id}
                    className={`flex items-stretch border-b border-white/5 ${
                      selectedId === r.id ? "bg-white/10" : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedId(r.id)}
                      className="min-w-0 flex-1 px-3 py-2 text-left text-sm hover:bg-white/5"
                    >
                      <div className="font-medium text-white">{r.suite}</div>
                      <div className="text-xs text-surface-muted">
                        {r.status}
                        {r.summary_json
                          ? ` · ${r.summary_json.passed}/${r.summary_json.executed} pass`
                          : ""}
                        {r.user_id
                          ? ` · ${tenantUsers.find((u) => u.id === r.user_id)?.email || r.user_id.slice(0, 8)}`
                          : ""}
                      </div>
                    </button>
                    {r.status === "queued" || r.status === "running" ? (
                      <button
                        type="button"
                        disabled={cancellingRunId === r.id}
                        title={t("admin:benchCancelRun")}
                        aria-label={t("admin:benchCancelRun")}
                        onClick={() => void onCancelRun(r)}
                        className="shrink-0 px-2 text-rose-400/90 hover:bg-rose-950/40 hover:text-rose-300 disabled:opacity-50"
                      >
                        {cancellingRunId === r.id ? "…" : "■"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={
                        deletingRunId === r.id ||
                        r.status === "queued" ||
                        r.status === "running"
                      }
                      title={
                        r.status === "queued" || r.status === "running"
                          ? t("admin:benchDeleteRunActive")
                          : t("admin:benchDeleteRun")
                      }
                      aria-label={t("admin:benchDeleteRun")}
                      onClick={() => requestDeleteRun(r)}
                      className="shrink-0 px-2 text-surface-muted hover:bg-rose-950/40 hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      {deletingRunId === r.id ? (
                        <span className="text-[10px]">…</span>
                      ) : (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="h-4 w-4"
                          aria-hidden
                        >
                          <path
                            fillRule="evenodd"
                            d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-xl border border-surface-border bg-surface-raised/40 p-4">
            {!detail ? (
              <p className="text-sm text-surface-muted">{t("admin:benchSelectRun")}</p>
            ) : (
              <>
                <h2 className="text-sm font-medium text-white">
                  {detail.suite} · {detail.status}
                </h2>
                {detail.status === "queued" || detail.status === "running" ? (
                  <button
                    type="button"
                    disabled={cancellingRunId === detail.id}
                    onClick={() => void onCancelRun(detail)}
                    className="mt-2 rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-950/50 disabled:opacity-50"
                  >
                    {cancellingRunId === detail.id
                      ? t("admin:benchCancelling")
                      : t("admin:benchCancelRun")}
                  </button>
                ) : null}
                {detail.error_text ? (
                  <p className="mt-2 text-sm text-red-400">{detail.error_text}</p>
                ) : null}
                {detail.resource_prefix ? (
                  <p className="mt-1 text-xs font-mono text-surface-muted">
                    prefix: {detail.resource_prefix}
                  </p>
                ) : null}
                {detail.status === "running" || detail.status === "queued" ? (
                  <div className="mt-2 space-y-1 text-xs text-sky-400/90">
                    <p>
                      {t("admin:benchRunLive")}
                      {(detail.summary_json?.executed ?? 0) > 0
                        ? ` · ${detail.summary_json?.passed ?? 0}/${detail.summary_json?.executed ?? 0} ${t("admin:benchRunLiveProgress")}`
                        : ""}
                    </p>
                    {detail.report_json?.in_flight ? (
                      <p className="font-mono text-[11px] text-sky-300/95">
                        {t("admin:benchInFlightNow")}: {detail.report_json.in_flight.scenario_id}{" "}
                        · {formatInFlightProviderModel(detail.report_json.in_flight)} ·{" "}
                        {formatInFlightActivity(detail.report_json.in_flight, t)}
                        {(() => {
                          const tok = formatInFlightPromptTokens(detail.report_json!.in_flight!);
                          return tok ? ` · ${t("admin:benchInFlightPromptTokens")} ${tok}` : "";
                        })()}
                        {(() => {
                          const ms = formatInFlightElapsed(detail.report_json!.in_flight!);
                          return ms != null ? ` · ${ms} ms` : "";
                        })()}
                      </p>
                    ) : null}
                    {detail.report_json?.in_flight &&
                    formatInFlightPreview(detail.report_json.in_flight) ? (
                      <p
                        className="font-mono text-[10px] leading-snug text-sky-200/70 truncate max-w-full"
                        title={detail.report_json.in_flight.generation_preview}
                      >
                        {t("admin:benchInFlightPreview")}:{" "}
                        {formatInFlightPreview(detail.report_json.in_flight)}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {(detail.report_json?.results?.length ?? 0) > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded border border-white/15 bg-black/30 px-2.5 py-1 text-[11px] text-white/90 hover:bg-white/10"
                      onClick={() => downloadFailuresCsv(detail)}
                    >
                      {t("admin:benchExportFailuresCsv")}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/15 bg-black/30 px-2.5 py-1 text-[11px] text-white/90 hover:bg-white/10"
                      onClick={() => downloadFailuresJson(detail)}
                    >
                      {t("admin:benchExportFailuresJson")}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/15 bg-black/30 px-2.5 py-1 text-[11px] text-white/90 hover:bg-white/10"
                      onClick={() => downloadFullReportJson(detail)}
                    >
                      {t("admin:benchExportFullJson")}
                    </button>
                  </div>
                ) : null}
                <BenchmarkFailuresSummary
                  rows={failuresFromResults(detail.report_json?.results ?? [])}
                  t={t}
                />
                <table className="mt-4 w-full text-left text-xs">
                  <thead>
                    <tr className="text-surface-muted">
                      <th className="py-1 pr-2 w-8" aria-label={t("admin:benchColDetail")} />
                      <th className="py-1 pr-2">{t("admin:benchColScenario")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColProviderModel")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColResult")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColTools")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColCompaction")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColCtx")}</th>
                      <th className="py-1 pr-2">{t("admin:benchColMs")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.report_json?.results ?? []).length === 0 &&
                    !detail.report_json?.in_flight &&
                    (detail.status === "running" || detail.status === "queued") ? (
                      <tr>
                        <td colSpan={8} className="py-3 text-surface-muted">
                          {t("admin:benchRunWaitingResults")}
                        </td>
                      </tr>
                    ) : null}
                    {detail.report_json?.in_flight ? (
                      <tr className="border-t border-sky-500/20 bg-sky-500/5">
                        <td className="py-1.5 pr-1 align-top text-sky-400" aria-hidden>
                          ◉
                        </td>
                        <td className="py-1.5 pr-2 font-mono text-sky-300">
                          {detail.report_json.in_flight.scenario_id}
                        </td>
                        <td className="py-1.5 pr-2 font-mono text-[11px] text-sky-300/90">
                          {formatInFlightProviderModel(detail.report_json.in_flight)}
                        </td>
                        <td className="py-1.5 pr-2 text-sky-300">
                          {t("admin:benchInFlightRunning")} —{" "}
                          {formatInFlightActivity(detail.report_json.in_flight, t)}
                        </td>
                        <td className="py-1.5 pr-2 text-sky-300/90">
                          {formatInFlightToolsColumn(detail.report_json.in_flight, t)}
                          {(detail.report_json.in_flight.tool_names?.length ?? 0) > 0 ? (
                            <span className="ml-1 text-surface-muted">
                              ({detail.report_json.in_flight.tool_names!.slice(-3).join(", ")})
                            </span>
                          ) : null}
                          {typeof detail.report_json.in_flight.forwarded_tool_count ===
                            "number" &&
                          detail.report_json.in_flight.forwarded_tool_count > 0 ? (
                            <span className="ml-1 block text-[10px] text-surface-muted">
                              → {detail.report_json.in_flight.forwarded_tool_count}{" "}
                              {t("admin:benchInFlightForwardedTools")}
                              {detail.report_json.in_flight.routed_category
                                ? ` (${detail.report_json.in_flight.routed_category})`
                                : ""}
                            </span>
                          ) : null}
                        </td>
                        <td className="py-1.5 pr-2 text-surface-muted">—</td>
                        <td className="py-1.5 pr-2 font-mono text-[11px] text-sky-300/90">
                          {formatInFlightPromptTokens(detail.report_json.in_flight) ?? "—"}
                        </td>
                        <td className="py-1.5 pr-2 text-sky-300/90">
                          {formatInFlightElapsed(detail.report_json.in_flight) ?? "…"}
                        </td>
                      </tr>
                    ) : null}
                    {(detail.report_json?.results ?? []).map((res, i) => {
                      const rowKey = `${res.scenario_id}-${i}`;
                      const expanded = expandedResultKey === rowKey;
                      const canExpand = scenarioHasDiagnostics(res) || Boolean(res.failure_reason);
                      return (
                        <Fragment key={rowKey}>
                          <tr className="border-t border-white/5">
                            <td className="py-1.5 pr-1 align-top">
                              {canExpand ? (
                                <button
                                  type="button"
                                  className="rounded px-1 text-surface-muted hover:bg-white/5 hover:text-white"
                                  aria-expanded={expanded}
                                  title={
                                    expanded
                                      ? t("admin:benchDetailCollapse")
                                      : t("admin:benchDetailExpand")
                                  }
                                  onClick={() =>
                                    setExpandedResultKey(expanded ? null : rowKey)
                                  }
                                >
                                  {expanded ? "▾" : "▸"}
                                </button>
                              ) : null}
                            </td>
                            <td className="py-1.5 pr-2 font-mono">{res.scenario_id}</td>
                            <td className="py-1.5 pr-2 font-mono text-[11px]">
                              {formatBenchmarkProviderModel(res)}
                            </td>
                            <td className="py-1.5 pr-2">
                              {res.run_metrics?.project_run_status
                                ? `${res.run_metrics.project_run_status} · `
                                : ""}
                              {res.skipped ? "SKIP" : res.passed ? "PASS" : "FAIL"}
                              {!res.skipped && !res.passed ? (
                                <span className="ml-1 text-surface-muted">
                                  — {formatResultFailureLine(res, t)}
                                </span>
                              ) : res.failure_reason ? (
                                <span className="ml-1 text-surface-muted">
                                  — {res.failure_reason}
                                </span>
                              ) : null}
                            </td>
                            <td className="py-1.5 pr-2">
                              {res.tool_call_count ?? 0}
                              {res.run_metrics?.llm_round_count != null
                                ? ` · ${res.run_metrics.llm_round_count} llm`
                                : ""}
                            </td>
                            <td className="py-1.5 pr-2">
                              {res.run_metrics?.compaction_count ?? 0}
                              {(res.run_metrics?.compaction_events?.length ?? 0) > 0 ? (
                                <span className="ml-1 text-surface-muted">
                                  (
                                  {(res.run_metrics?.compaction_events ?? [])
                                    .map((e) => e.phase)
                                    .filter(Boolean)
                                    .join(", ")}
                                  )
                                </span>
                              ) : null}
                            </td>
                            <td className="py-1.5 pr-2">
                              {res.run_metrics?.context_utilization_pct != null
                                ? `${res.run_metrics.context_utilization_pct}%`
                                : "—"}
                            </td>
                            <td className="py-1.5 pr-2">{Math.round(res.latency_ms)}</td>
                          </tr>
                          {expanded ? (
                            <tr className="border-t border-white/5">
                              <td colSpan={8} className="py-2 pr-2">
                                <BenchmarkScenarioDetail res={res} t={t} />
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      ) : null}

      <ConfirmModal
        open={deleteRunTarget != null}
        title={t("admin:benchDeleteRunTitle")}
        description={
          deleteRunTarget
            ? t("admin:benchDeleteRunDescription", {
                suite: deleteRunTarget.suite || deleteRunTarget.id.slice(0, 8),
              })
            : ""
        }
        confirmLabel={t("admin:benchDeleteRunConfirmAction")}
        cancelLabel={t("admin:cancel")}
        variant="danger"
        busy={deletingRunId != null}
        onConfirm={() => void confirmDeleteRun()}
        onCancel={() => {
          if (!deletingRunId) setDeleteRunTarget(null);
        }}
      />
    </div>
  );
}
