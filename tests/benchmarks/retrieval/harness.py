"""Run retrieval benchmarks and aggregate metrics."""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from tests.benchmarks.retrieval.cases import BenchmarkCase
from tests.benchmarks.retrieval.scoring import (
    extract_candidates,
    hit_at_k,
    tool_calls_for_strategy,
)


@dataclass
class CaseResult:
    case_id: str
    strategy: str
    query: str
    hit: bool
    first_rank: int | None
    hit_sources: list[str]
    tool_calls: int
    candidate_count: int
    latency_ms: float
    k: int
    error: str | None = None


@dataclass
class BenchReport:
    strategy: str
    workspace_path: str
    case_count: int
    hits: int
    hit_rate: float
    hit_at_k: float
    mean_tool_calls: float
    p50_latency_ms: float
    p95_latency_ms: float
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cases"] = [asdict(c) for c in self.cases]
        return d


def _workspace_context(workspace_path: str, workspace_id: str | None = None) -> dict[str, Any]:
    wid = workspace_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, workspace_path))
    return {
        "workspace": {
            "id": wid,
            "path": workspace_path,
            "semantic_index_enabled": True,
            "retrieval_enabled": True,
        }
    }


def _run_unified(case: BenchmarkCase, ctx: dict[str, Any]) -> tuple[dict[str, Any], float]:
    from plugins.tools.workspace.search.retrieve_context import retrieve_context

    t0 = time.perf_counter()
    raw = retrieve_context(
        {
            "query": case.query,
            "sources": case.sources,
            "grep_limit": case.k,
            "semantic_limit": case.k,
            "docs_limit": min(case.k, 30),
        },
        context=ctx,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return json.loads(raw), elapsed_ms


def _run_separate(case: BenchmarkCase, ctx: dict[str, Any]) -> tuple[dict[str, Any], float]:
    from plugins.tools.workspace.search.retrieve_context import retrieve_context as rc

    t0 = time.perf_counter()
    bundle: dict[str, Any] = {"ok": True, "query": case.query, "sources_requested": case.sources}

    if "code_grep" in case.sources:
        bundle["code_grep"] = rc._run_code_grep(case.query, ctx, case.k)
    if "code_semantic" in case.sources:
        bundle["code_semantic"] = rc._run_code_semantic(case.query, ctx, case.k)
    if "docs" in case.sources:
        bundle["docs"] = rc._run_docs(case.query, "agentlayer_docs", min(case.k, 30))
    if "memory" in case.sources:
        bundle["memory"] = rc._run_memory(case.query, min(case.k, 20))

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return bundle, elapsed_ms


_RUNNERS: dict[str, Callable[[BenchmarkCase, dict[str, Any]], tuple[dict[str, Any], float]]] = {
    "unified": _run_unified,
    "separate": _run_separate,
}


def run_case(
    case: BenchmarkCase,
    *,
    strategy: str,
    workspace_path: str,
    workspace_id: str | None = None,
) -> CaseResult:
    runner = _RUNNERS.get(strategy)
    if runner is None:
        raise ValueError(f"unknown strategy: {strategy}")

    ctx = _workspace_context(workspace_path, workspace_id)
    tool_calls = tool_calls_for_strategy(strategy, case.sources)
    err: str | None = None
    bundle: dict[str, Any] = {}
    latency_ms = 0.0

    try:
        bundle, latency_ms = runner(case, ctx)
        if not bundle.get("ok", True):
            err = str(bundle.get("error") or bundle.get("reason") or "not ok")
    except Exception as e:
        err = str(e)[:300]

    candidates = extract_candidates(bundle) if not err else []
    hit, first_rank, hit_sources = hit_at_k(
        candidates,
        case.needles,
        k=case.k,
        match_all=case.match_all_needles,
    )

    return CaseResult(
        case_id=case.id,
        strategy=strategy,
        query=case.query,
        hit=hit and err is None,
        first_rank=first_rank,
        hit_sources=hit_sources,
        tool_calls=tool_calls,
        candidate_count=len(candidates),
        latency_ms=round(latency_ms, 2),
        k=case.k,
        error=err,
    )


def run_suite(
    cases: list[BenchmarkCase],
    *,
    strategy: str,
    workspace_path: str,
    workspace_id: str | None = None,
) -> BenchReport:
    results: list[CaseResult] = []
    for case in cases:
        results.append(
            run_case(
                case,
                strategy=strategy,
                workspace_path=workspace_path,
                workspace_id=workspace_id,
            )
        )

    hits = sum(1 for r in results if r.hit)
    n = len(results) or 1
    latencies = sorted(r.latency_ms for r in results)

    def _pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(p * len(latencies)))
        return latencies[idx]

    return BenchReport(
        strategy=strategy,
        workspace_path=workspace_path,
        case_count=len(results),
        hits=hits,
        hit_rate=round(hits / n, 4),
        hit_at_k=round(hits / n, 4),
        mean_tool_calls=round(
            statistics.mean([r.tool_calls for r in results]) if results else 0.0,
            2,
        ),
        p50_latency_ms=round(_pct(0.5), 2),
        p95_latency_ms=round(_pct(0.95), 2),
        cases=results,
    )


def compare_strategies(
    cases: list[BenchmarkCase],
    *,
    workspace_path: str,
) -> dict[str, BenchReport]:
    return {
        "unified": run_suite(cases, strategy="unified", workspace_path=workspace_path),
        "separate": run_suite(cases, strategy="separate", workspace_path=workspace_path),
    }
