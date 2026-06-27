"""Cross-run benchmark analysis grouped by cohort / fingerprint."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from apps.backend.infrastructure.benchmarks.benchmark_stats import aggregate_benchmark_stats


def _attempt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        report = row.get("report_json")
        if not isinstance(report, dict):
            continue
        results = report.get("results")
        if not isinstance(results, list):
            continue
        for entry in results:
            if not isinstance(entry, dict):
                continue
            sid = str(entry.get("scenario_id") or entry.get("id") or "")
            attempts = entry.get("attempts") if isinstance(entry.get("attempts"), list) else [entry]
            for att in attempts:
                if isinstance(att, dict):
                    merged = dict(att)
                    merged.setdefault("scenario_id", sid)
                    out.append(merged)
    return out


def _pattern_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    try:
        from tests.benchmarks.agent.patterns import aggregate_patterns

        return aggregate_patterns(_attempt_rows(rows))
    except Exception:
        return {}


def _cohort_label_from_run(row: dict[str, Any]) -> str | None:
    cohort = row.get("cohort_json")
    if isinstance(cohort, dict):
        label = str(cohort.get("cohort_label") or cohort.get("label") or "").strip()
        if label:
            return label
    return None


def _fingerprint_from_run(row: dict[str, Any]) -> str | None:
    cohort = row.get("cohort_json")
    if isinstance(cohort, dict):
        fp = str(cohort.get("fingerprint") or "").strip()
        if fp:
            return fp
    return None


def list_cohorts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        label = _cohort_label_from_run(row)
        if label:
            counts[label] += 1
    return [{"cohort_label": k, "run_count": v} for k, v in sorted(counts.items())]


def analyze_runs(
    rows: list[dict[str, Any]],
    *,
    cohort: str | None = None,
    fingerprint: str | None = None,
    suite: str | None = None,
    since_days: int | None = None,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if suite and str(row.get("suite") or "") != suite:
            continue
        if cohort and _cohort_label_from_run(row) != cohort:
            continue
        if fingerprint and _fingerprint_from_run(row) != fingerprint:
            continue
        if experiment_id:
            cj = row.get("cohort_json") if isinstance(row.get("cohort_json"), dict) else {}
            if str(cj.get("experiment_id") or "") != experiment_id:
                continue
        filtered.append(row)

    stats = aggregate_benchmark_stats(filtered, suite_filter=suite, since_days=since_days)
    patterns = _pattern_summary(filtered)
    by_scenario: list[dict[str, Any]] = []
    scenario_groups: dict[str, list[dict[str, Any]]] = {}
    for att in _attempt_rows(filtered):
        sid = str(att.get("scenario_id") or "unknown")
        scenario_groups.setdefault(sid, []).append(att)
    try:
        from tests.benchmarks.agent.patterns import classify_failure

        for sid, attempts in sorted(scenario_groups.items()):
            pids: set[str] = set()
            fails = 0
            for att in attempts:
                if not att.get("passed", True):
                    fails += 1
                    pids.update(classify_failure(att))
            total = len(attempts)
            by_scenario.append(
                {
                    "scenario_id": sid,
                    "pass_rate": (total - fails) / total if total else 0.0,
                    "patterns": sorted(pids),
                }
            )
    except Exception:
        pass
    return {
        "run_count": len(filtered),
        "cohort": cohort,
        "fingerprint": fingerprint,
        "suite": suite,
        "stats": stats,
        "top_patterns": patterns,
        "by_scenario": by_scenario,
    }


def compare_cohorts(
    rows: list[dict[str, Any]],
    *,
    cohort_a: str,
    cohort_b: str,
    suite: str | None = None,
) -> dict[str, Any]:
    a_rows = [r for r in rows if _cohort_label_from_run(r) == cohort_a]
    b_rows = [r for r in rows if _cohort_label_from_run(r) == cohort_b]
    if suite:
        a_rows = [r for r in a_rows if str(r.get("suite") or "") == suite]
        b_rows = [r for r in b_rows if str(r.get("suite") or "") == suite]
    return {
        "cohort_a": cohort_a,
        "cohort_b": cohort_b,
        "suite": suite,
        "a": analyze_runs(a_rows, cohort=cohort_a, suite=suite),
        "b": analyze_runs(b_rows, cohort=cohort_b, suite=suite),
    }
