import type { BenchmarkAttemptSnapshot, BenchmarkScenarioResult } from "./benchmarksApi";

export function attemptsMaxFromResult(res: BenchmarkScenarioResult): number {
  return Math.max(1, Number(res.run_metrics?.attempts_max ?? 1));
}

export function attemptNumberFromResult(res: BenchmarkScenarioResult): number {
  return Math.max(1, Number(res.run_metrics?.attempt ?? 1));
}

export function attemptHistoryFromResult(
  res: BenchmarkScenarioResult,
): BenchmarkAttemptSnapshot[] {
  const hist = res.run_metrics?.attempt_history;
  if (!Array.isArray(hist) || hist.length === 0) {
    return [];
  }
  return hist.filter((x): x is BenchmarkAttemptSnapshot => x != null && typeof x === "object");
}

export function hasMultipleAttempts(res: BenchmarkScenarioResult): boolean {
  return attemptHistoryFromResult(res).length > 1;
}

/** Result line for the summary table: PASS · 2/3 */
export function formatBenchmarkResultStatus(res: BenchmarkScenarioResult): string {
  if (res.skipped) {
    return "SKIP";
  }
  const attemptsMax = attemptsMaxFromResult(res);
  const attempt = attemptNumberFromResult(res);
  const base = res.passed ? "PASS" : "FAIL";
  if (attemptsMax > 1) {
    return `${base} · ${attempt}/${attemptsMax}`;
  }
  return base;
}

export function passAt1FromResult(res: BenchmarkScenarioResult): boolean | null {
  if (res.skipped) {
    return null;
  }
  const hist = attemptHistoryFromResult(res);
  if (hist.length > 0) {
    return Boolean(hist[0]?.passed);
  }
  if (attemptsMaxFromResult(res) <= 1) {
    return null;
  }
  if (typeof res.run_metrics?.pass_at_1 === "boolean") {
    return res.run_metrics.pass_at_1;
  }
  if (attemptNumberFromResult(res) > 1) {
    return false;
  }
  return Boolean(res.passed);
}

export function scenarioResultForAttempt(
  base: BenchmarkScenarioResult,
  snap: BenchmarkAttemptSnapshot,
): BenchmarkScenarioResult {
  const rm = snap.run_metrics ?? {};
  return {
    ...base,
    passed: Boolean(snap.passed),
    skipped: Boolean(snap.skipped),
    failure_reason: snap.failure_reason ?? base.failure_reason,
    rubric_failure_reason: snap.rubric_failure_reason ?? base.rubric_failure_reason,
    transport_error: snap.transport_error ?? base.transport_error,
    latency_ms: Number(snap.latency_ms ?? base.latency_ms),
    tool_call_count: Number(snap.tool_call_count ?? base.tool_call_count),
    tool_names: Array.isArray(snap.tool_names) ? snap.tool_names : base.tool_names,
    agent_run_id: snap.agent_run_id ?? base.agent_run_id,
    assistant_excerpt: snap.assistant_excerpt ?? base.assistant_excerpt,
    assistant_content: snap.assistant_content ?? base.assistant_content,
    assistant_content_truncated:
      snap.assistant_content_truncated ?? base.assistant_content_truncated,
    scenario_prompt: snap.scenario_prompt?.trim() ? snap.scenario_prompt : base.scenario_prompt,
    run_metrics: {
      ...base.run_metrics,
      ...rm,
      attempt: snap.attempt,
      attempts_max: attemptsMaxFromResult(base),
    },
  };
}

export function effectiveScenarioForDetail(
  res: BenchmarkScenarioResult,
  attemptIndex: number,
): BenchmarkScenarioResult {
  const hist = attemptHistoryFromResult(res);
  if (hist.length === 0 || attemptIndex < 0 || attemptIndex >= hist.length) {
    return res;
  }
  return scenarioResultForAttempt(res, hist[attemptIndex]!);
}
