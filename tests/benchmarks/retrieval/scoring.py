"""Scoring helpers for retrieval benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievedCandidate:
    source: str
    rank: int
    path: str | None = None
    name: str | None = None
    text: str | None = None
    title: str | None = None


def _candidate_blob(c: RetrievedCandidate) -> str:
    parts = [c.source, c.path or "", c.name or "", c.text or "", c.title or ""]
    return " ".join(parts).lower()


def extract_candidates(bundle: dict[str, Any]) -> list[RetrievedCandidate]:
    """Flatten a ``retrieve_context`` bundle; prefers ``fused_ranking`` when present."""
    fused = bundle.get("fused_ranking")
    if isinstance(fused, list) and fused:
        out: list[RetrievedCandidate] = []
        for item in fused:
            if not isinstance(item, dict):
                continue
            rank = int(item.get("rank") or len(out) + 1)
            out.append(
                RetrievedCandidate(
                    source=str(item.get("source") or "fused"),
                    rank=rank,
                    path=str(item.get("path") or "") or None,
                    name=str(item.get("name") or "") or None,
                    text=str(item.get("text") or "") or None,
                    title=str(item.get("title") or "") or None,
                )
            )
        return out

    out = []
    rank = 0

    grep = bundle.get("code_grep")
    if isinstance(grep, dict) and grep.get("ok"):
        for m in grep.get("matches") or []:
            if not isinstance(m, dict):
                continue
            rank += 1
            out.append(
                RetrievedCandidate(
                    source="code_grep",
                    rank=rank,
                    path=str(m.get("path") or ""),
                    text=str(m.get("text") or ""),
                )
            )

    sem = bundle.get("code_semantic")
    if isinstance(sem, dict) and sem.get("ok"):
        for r in sem.get("results") or []:
            if not isinstance(r, dict):
                continue
            rank += 1
            out.append(
                RetrievedCandidate(
                    source="code_semantic",
                    rank=rank,
                    path=str(r.get("file_path") or r.get("path") or ""),
                    name=str(r.get("name") or ""),
                    text=str(r.get("signature") or r.get("text") or ""),
                )
            )

    docs = bundle.get("docs")
    if isinstance(docs, dict) and docs.get("ok"):
        for h in docs.get("hits") or []:
            if not isinstance(h, dict):
                continue
            rank += 1
            out.append(
                RetrievedCandidate(
                    source="docs",
                    rank=rank,
                    title=str(h.get("title") or ""),
                    text=str(h.get("text") or h.get("chunk") or ""),
                )
            )

    mem = bundle.get("memory")
    if isinstance(mem, dict) and mem.get("ok"):
        for n in mem.get("notes") or []:
            if not isinstance(n, dict):
                continue
            rank += 1
            out.append(
                RetrievedCandidate(
                    source="memory",
                    rank=rank,
                    text=str(n.get("text") or ""),
                )
            )

    return out


def hit_at_k(
    candidates: list[RetrievedCandidate],
    needles: list[str],
    *,
    k: int,
    match_all: bool = False,
) -> tuple[bool, int | None, list[str]]:
    """
    Return (hit, first_rank, sources_that_matched).

    A needle matches if its lowercase form appears in the candidate blob.
    """
    if not needles:
        return True, 1 if candidates else None, []

    top = candidates[: max(1, k)]
    matched_sources: set[str] = set()
    first_rank: int | None = None
    needles_l = [n.lower() for n in needles if n.strip()]

    for c in top:
        blob = _candidate_blob(c)
        for needle in needles_l:
            if needle in blob:
                matched_sources.add(c.source)
                if first_rank is None:
                    first_rank = c.rank

    if match_all:
        hit = all(
            any(n in _candidate_blob(c) for c in top)
            for n in needles_l
        )
    else:
        hit = bool(matched_sources)

    return hit, first_rank, sorted(matched_sources)


def tool_calls_for_strategy(strategy: str, sources: list[str]) -> int:
    if strategy == "unified":
        return 1
    if strategy == "separate":
        return max(1, len(sources))
    raise ValueError(f"unknown strategy: {strategy}")
