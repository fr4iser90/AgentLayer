"""Aggregate benchmark run results for admin stats / leaderboard."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _pass_rate(pass_count: int, sample_count: int) -> float | None:
    if sample_count <= 0:
        return None
    return round(pass_count / sample_count, 4)


def _extract_result_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("id") or "")
        suite = str(run.get("suite") or "")
        finished_at = run.get("finished_at") or run.get("created_at")
        report = run.get("report_json")
        if not isinstance(report, dict):
            continue
        results = report.get("results")
        if not isinstance(results, list):
            continue
        for raw in results:
            if not isinstance(raw, dict):
                continue
            scenario_id = str(raw.get("scenario_id") or "").strip()
            catalog = str(raw.get("catalog_owned_by") or "").strip()
            model = str(raw.get("model") or "").strip()
            if not scenario_id:
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "suite": suite,
                    "finished_at": finished_at,
                    "scenario_id": scenario_id,
                    "profile_label": str(raw.get("profile_label") or "").strip(),
                    "catalog_owned_by": catalog,
                    "model": model,
                    "passed": bool(raw.get("passed")),
                    "skipped": bool(raw.get("skipped")),
                    "score": float(raw.get("score") or 0.0),
                    "latency_ms": max(0.0, float(raw.get("latency_ms") or 0.0)),
                }
            )
    return rows


def _finalize_cell(
    *,
    catalog_owned_by: str,
    model: str,
    profile_labels: list[str],
    sample_count: int,
    skip_count: int,
    pass_count: int,
    run_ids: set[str],
    latencies: list[float],
    scores: list[float],
) -> dict[str, Any]:
    label_counts = Counter(l for l in profile_labels if l)
    profile_label = label_counts.most_common(1)[0][0] if label_counts else catalog_owned_by
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    med_latency = _median(latencies)
    return {
        "catalog_owned_by": catalog_owned_by,
        "model": model,
        "profile_label": profile_label,
        "runs": len(run_ids),
        "samples": sample_count,
        "skipped": skip_count,
        "passed": pass_count,
        "pass_rate": _pass_rate(pass_count, sample_count),
        "avg_latency_ms": avg_latency,
        "median_latency_ms": round(med_latency, 1) if med_latency is not None else None,
        "min_latency_ms": round(min(latencies), 1) if latencies else None,
        "max_latency_ms": round(max(latencies), 1) if latencies else None,
        "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
    }


def _sort_model_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple:
        rate = row.get("pass_rate")
        rate_key = -(rate if isinstance(rate, (int, float)) else -1.0)
        avg = row.get("avg_latency_ms")
        avg_key = avg if isinstance(avg, (int, float)) else 1e12
        return (rate_key, avg_key, str(row.get("catalog_owned_by") or ""), str(row.get("model") or ""))

    return sorted(rows, key=key)


def _row_meets_min_samples(row: dict[str, Any], badge_min_samples: int) -> bool:
    return int(row.get("samples") or 0) >= max(1, int(badge_min_samples))


def _row_meets_pass_threshold(row: dict[str, Any], min_pass_rate: float) -> bool:
    samples = int(row.get("samples") or 0)
    passed = int(row.get("passed") or 0)
    if samples <= 0:
        return False
    threshold = max(0.0, min(1.0, float(min_pass_rate)))
    if threshold <= 0.0:
        return passed > 0
    return (passed / samples) >= threshold


def _pick_fastest_badge(
    ranked: list[dict[str, Any]],
    *,
    badge_min_samples: int,
    fastest_min_pass_rate: float,
) -> dict[str, Any] | None:
    fastest: dict[str, Any] | None = None
    for row in ranked:
        if not _row_meets_min_samples(row, badge_min_samples):
            continue
        if not _row_meets_pass_threshold(row, fastest_min_pass_rate):
            continue
        avg = row.get("avg_latency_ms")
        if avg is None:
            continue
        if fastest is None or avg < fastest["avg_latency_ms"]:
            fastest = {
                "catalog_owned_by": row["catalog_owned_by"],
                "model": row["model"],
                "profile_label": row["profile_label"],
                "avg_latency_ms": avg,
                "pass_rate": row.get("pass_rate"),
                "samples": row.get("samples"),
            }
    return fastest


def _pick_best_pass_badge(
    ranked: list[dict[str, Any]],
    *,
    badge_min_samples: int,
) -> dict[str, Any] | None:
    for row in ranked:
        if not _row_meets_min_samples(row, badge_min_samples):
            continue
        if row.get("pass_rate") != 1.0:
            continue
        return {
            "catalog_owned_by": row["catalog_owned_by"],
            "model": row["model"],
            "profile_label": row["profile_label"],
            "pass_rate": row.get("pass_rate"),
            "samples": row.get("samples"),
        }
    return None


def aggregate_benchmark_stats(
    runs: list[dict[str, Any]],
    *,
    suite_filter: str | None = None,
    since_days: int | None = None,
    badge_min_samples: int = 1,
    fastest_min_pass_rate: float = 0.0,
) -> dict[str, Any]:
    """Aggregate by model and by (suite, scenario, model)."""
    suite_norm = (suite_filter or "").strip() or None
    filtered_runs = runs
    if suite_norm:
        filtered_runs = [r for r in runs if str(r.get("suite") or "") == suite_norm]

    rows = _extract_result_rows(filtered_runs)
    suites_seen = sorted({str(r.get("suite") or "") for r in filtered_runs if r.get("suite")})

    model_cells: dict[tuple[str, str], dict[str, Any]] = {}
    scenario_cells: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in rows:
        catalog = row["catalog_owned_by"] or "unknown"
        model = row["model"] or "—"
        model_key = (catalog, model)

        for bucket, key in (
            (model_cells, model_key),
            (scenario_cells, (row["suite"], row["scenario_id"], catalog, model)),
        ):
            cell = bucket.get(key)
            if cell is None:
                cell = {
                    "catalog_owned_by": catalog,
                    "model": model,
                    "profile_labels": [],
                    "sample_count": 0,
                    "skip_count": 0,
                    "pass_count": 0,
                    "run_ids": set(),
                    "latencies": [],
                    "scores": [],
                }
                bucket[key] = cell
            cell["profile_labels"].append(row["profile_label"])
            cell["run_ids"].add(row["run_id"])
            if row["skipped"]:
                cell["skip_count"] += 1
                continue
            cell["sample_count"] += 1
            if row["passed"]:
                cell["pass_count"] += 1
            cell["latencies"].append(row["latency_ms"])
            cell["scores"].append(row["score"])

    models = _sort_model_rows(
        [
            _finalize_cell(
                catalog_owned_by=k[0],
                model=k[1],
                profile_labels=v["profile_labels"],
                sample_count=v["sample_count"],
                skip_count=v["skip_count"],
                pass_count=v["pass_count"],
                run_ids=v["run_ids"],
                latencies=v["latencies"],
                scores=v["scores"],
            )
            for k, v in model_cells.items()
            if v["sample_count"] > 0 or v["skip_count"] > 0
        ]
    )

    by_scenario_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (suite, scenario_id, catalog, model), v in scenario_cells.items():
        if v["sample_count"] <= 0 and v["skip_count"] <= 0:
            continue
        finalized = _finalize_cell(
            catalog_owned_by=catalog,
            model=model,
            profile_labels=v["profile_labels"],
            sample_count=v["sample_count"],
            skip_count=v["skip_count"],
            pass_count=v["pass_count"],
            run_ids=v["run_ids"],
            latencies=v["latencies"],
            scores=v["scores"],
        )
        by_scenario_map.setdefault((suite, scenario_id), []).append(finalized)

    by_scenario: list[dict[str, Any]] = []
    badge_min = max(1, int(badge_min_samples))
    fastest_threshold = max(0.0, min(1.0, float(fastest_min_pass_rate)))
    for (suite, scenario_id), model_rows in sorted(by_scenario_map.items(), key=lambda x: x[0]):
        ranked = _sort_model_rows(model_rows)
        fastest = _pick_fastest_badge(
            ranked,
            badge_min_samples=badge_min,
            fastest_min_pass_rate=fastest_threshold,
        )
        best_pass = _pick_best_pass_badge(ranked, badge_min_samples=badge_min)
        by_scenario.append(
            {
                "suite": suite,
                "scenario_id": scenario_id,
                "models": ranked,
                "fastest": fastest,
                "best_pass": best_pass,
            }
        )

    run_ids = {str(r.get("id") or "") for r in filtered_runs if r.get("id")}
    return {
        "meta": {
            "run_count": len(run_ids),
            "result_count": len(rows),
            "suite_filter": suite_norm,
            "since_days": since_days,
            "badge_min_samples": badge_min,
            "fastest_min_pass_rate": fastest_threshold,
            "suites": suites_seen,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "models": models,
        "by_scenario": by_scenario,
    }
