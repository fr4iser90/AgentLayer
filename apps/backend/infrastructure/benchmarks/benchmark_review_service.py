"""Shared benchmark review logic (HTTP, reviewer agent, jobs)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.agent_runtime import agent_config_store
from apps.backend.infrastructure.benchmarks import benchmark_runs_store
from apps.backend.infrastructure.benchmarks.benchmark_analysis import analyze_runs
from apps.backend.infrastructure.agent_runtime.agent_config_fingerprint import compute_fingerprint
from tests.benchmarks.agent.patterns import aggregate_patterns, classify_failure


def _attempt_results_from_run(row: dict[str, Any]) -> list[dict[str, Any]]:
    report = row.get("report_json")
    if not isinstance(report, dict):
        return []
    results = report.get("results")
    if not isinstance(results, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        scenario_id = str(entry.get("scenario_id") or entry.get("id") or "")
        attempts = entry.get("attempts") if isinstance(entry.get("attempts"), list) else [entry]
        for att in attempts:
            if not isinstance(att, dict):
                continue
            merged = dict(att)
            merged.setdefault("scenario_id", scenario_id)
            out.append(merged)
    return out


def _verdict_from_analysis(analysis: dict[str, Any], patterns: dict[str, int]) -> str:
    run_count = int(analysis.get("run_count") or 0)
    if run_count == 0:
        return "needs_more_data"
    stats = analysis.get("stats") if isinstance(analysis.get("stats"), dict) else {}
    models = stats.get("models") if isinstance(stats.get("models"), list) else []
    if not models:
        return "inconclusive"
    top = models[0] if isinstance(models[0], dict) else {}
    pass_rate = float(top.get("pass_rate") or 0.0)
    if pass_rate >= 0.85:
        return "accept"
    if pass_rate >= 0.5:
        return "mixed"
    if patterns.get("A1_no_tool_call", 0) >= 3:
        return "regression_tool_calling"
    return "reject"


def run_review(
    *,
    tenant_id: int,
    experiment_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    run_ids: list[uuid.UUID] | None = None,
    mode: str = "deterministic",
    reviewer_model: str | None = None,
    actor_type: str = "reviewer_job",
    summary_hint: str | None = None,
) -> dict[str, Any]:
    rows = benchmark_runs_store.list_runs_for_stats(tenant_id=tenant_id, limit=500)
    if run_ids:
        wanted = {str(r) for r in run_ids}
        rows = [r for r in rows if str(r.get("id")) in wanted]

    analysis = analyze_runs(
        rows,
        experiment_id=str(experiment_id) if experiment_id else None,
    )
    all_attempts: list[dict[str, Any]] = []
    for row in rows:
        all_attempts.extend(_attempt_results_from_run(row))
    patterns = aggregate_patterns(all_attempts)
    verdict = _verdict_from_analysis(analysis, patterns)
    fingerprint = compute_fingerprint(tenant_id=tenant_id)

    by_scenario: dict[str, list[str]] = {}
    for att in all_attempts:
        sid = str(att.get("scenario_id") or "unknown")
        for pid in classify_failure(att):
            by_scenario.setdefault(sid, [])
            if pid not in by_scenario[sid]:
                by_scenario[sid].append(pid)

    summary_parts = []
    if summary_hint:
        summary_parts.append(summary_hint.strip())
    if mode == "llm":
        model_label = reviewer_model or "unspecified reviewer model"
        summary_parts.append(
            f"LLM reviewer requested ({model_label}); deterministic benchmark analysis used as fallback."
        )
    summary_parts.append(f"Reviewed {analysis.get('run_count', 0)} run(s); verdict={verdict}.")
    if patterns:
        top = sorted(patterns.items(), key=lambda kv: -kv[1])[:5]
        summary_parts.append("Top patterns: " + ", ".join(f"{k}({v})" for k, v in top))

    output_payload = {
        "verdict": verdict,
        "summary": " ".join(summary_parts),
        "analysis": analysis,
        "patterns": patterns,
        "by_scenario_patterns": by_scenario,
        "fingerprint": fingerprint,
        "mode": mode,
        "reviewer_model": reviewer_model,
        "llm_review_status": "fallback_deterministic" if mode == "llm" else None,
    }
    input_payload = {
        "experiment_id": str(experiment_id) if experiment_id else None,
        "session_id": str(session_id) if session_id else None,
        "run_ids": [str(r) for r in (run_ids or [])],
    }
    review = agent_config_store.create_review(
        tenant_id=tenant_id,
        experiment_id=experiment_id,
        session_id=session_id,
        mode=mode,
        reviewer_model=reviewer_model,
        input_payload=input_payload,
        output_payload=output_payload,
        actor_type=actor_type,
    )
    return review
