"""Benchmark query cases (fixture workspace + optional live AgentLayer repo)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    query: str
    needles: list[str]
    sources: list[str] = field(default_factory=lambda: ["code_grep", "code_semantic"])
    k: int = 8
    match_all_needles: bool = False
    live_only: bool = False
    fixture_only: bool = False


FIXTURE_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        id="grep_verify_token",
        query="bench_verify_token",
        needles=["verify_token", "auth/middleware"],
        sources=["code_grep"],
        fixture_only=True,
    ),
    BenchmarkCase(
        id="grep_login",
        query="bench_login_handler",
        needles=["routes.py", "bench_login"],
        sources=["code_grep"],
        fixture_only=True,
    ),
    BenchmarkCase(
        id="grep_retrieval_layer",
        query="retrieve_context bundles",
        needles=["retrieval_layer", "RETRIEVAL_LAYER_DOC"],
        sources=["code_grep"],
        fixture_only=True,
    ),
    BenchmarkCase(
        id="unified_auth_middleware",
        query="bench_verify_token",
        needles=["middleware", "verify_token"],
        sources=["code_grep", "code_semantic"],
        k=8,
    ),
    BenchmarkCase(
        id="unified_retrieval_orchestration",
        query="bench_merge_retrieval",
        needles=["merge_retrieval", "retrieval_layer"],
        sources=["code_grep"],
        k=8,
    ),
]

# Live cases: run against repo root when RETRIEVAL_BENCH_LIVE=1 (needs index for semantic).
LIVE_REPO_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        id="live_retrieve_context_tool",
        query="retrieve_context unified retrieval tool",
        needles=["retrieve_context.py", "retrieve_context"],
        sources=["code_grep", "code_semantic"],
        live_only=True,
    ),
    BenchmarkCase(
        id="live_rag_embedding_sync",
        query="rag embedding model startup sync",
        needles=["rag_embedding_sync"],
        sources=["code_grep", "code_semantic"],
        live_only=True,
    ),
    BenchmarkCase(
        id="live_workspace_retrieval",
        query="workspace semantic index Qdrant",
        needles=["workspace_retrieval"],
        sources=["code_grep", "code_semantic"],
        live_only=True,
    ),
    BenchmarkCase(
        id="live_retrieval_bar_ui",
        query="WorkspaceRetrievalBar index progress",
        needles=["WorkspaceRetrievalBar"],
        sources=["code_grep"],
        live_only=True,
    ),
    BenchmarkCase(
        id="live_retrieval_docs",
        query="retrieval layer architecture grep semantic",
        needles=["retrieval-layer", "retrieval layer"],
        sources=["docs"],
        k=6,
        live_only=True,
    ),
]


def fixture_workspace_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_mini"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def cases_for_run(*, live: bool) -> list[BenchmarkCase]:
    if live:
        return list(FIXTURE_CASES) + list(LIVE_REPO_CASES)
    return [c for c in FIXTURE_CASES if not c.live_only]
