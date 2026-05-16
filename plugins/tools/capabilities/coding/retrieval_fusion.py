"""RRF fusion for ``retrieve_context`` sub-retriever results."""

from __future__ import annotations

from typing import Any

_RRF_K = 60


def _candidate_key(source: str, item: dict[str, Any]) -> str:
    if source in ("code_grep", "code_semantic"):
        path = item.get("path") or item.get("file_path")
        line = item.get("line")
        if path is not None and line is not None:
            return f"loc:{path}:{line}"
    if source == "code_grep":
        return f"grep:{item.get('path')}:{item.get('line')}"
    if source == "code_semantic":
        return f"sem:{item.get('file_path') or item.get('path')}:{item.get('line')}:{item.get('name')}"
    if source == "docs":
        return f"doc:{item.get('domain')}:{item.get('title')}:{item.get('chunk_index')}"
    if source == "memory":
        return f"mem:{item.get('id')}"
    return f"{source}:{hash(str(item))}"


def _item_to_fused(source: str, item: dict[str, Any], rrf_score: float, rank: int) -> dict[str, Any]:
    if source == "code_grep":
        return {
            "rank": rank,
            "source": source,
            "rrf_score": round(rrf_score, 6),
            "path": item.get("path"),
            "line": item.get("line"),
            "text": item.get("text"),
        }
    if source == "code_semantic":
        return {
            "rank": rank,
            "source": source,
            "rrf_score": round(rrf_score, 6),
            "path": item.get("file_path") or item.get("path"),
            "line": item.get("line"),
            "name": item.get("name"),
            "score": item.get("score"),
        }
    if source == "docs":
        return {
            "rank": rank,
            "source": source,
            "rrf_score": round(rrf_score, 6),
            "title": item.get("title"),
            "domain": item.get("domain"),
            "distance": item.get("distance"),
            "text": (item.get("text") or item.get("chunk") or "")[:500],
        }
    if source == "memory":
        return {
            "rank": rank,
            "source": source,
            "rrf_score": round(rrf_score, 6),
            "id": item.get("id"),
            "score": item.get("score"),
            "text": (item.get("text") or "")[:500],
        }
    return {"rank": rank, "source": source, "rrf_score": round(rrf_score, 6), "raw": item}


def reciprocal_rank_fusion(
    ranked_lists: list[tuple[str, list[dict[str, Any]]]],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Merge multiple ranked lists with RRF; dedupe by candidate key."""
    scores: dict[str, float] = {}
    best: dict[str, tuple[str, dict[str, Any]]] = {}

    for source, items in ranked_lists:
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            key = _candidate_key(source, item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + i + 1)
            if key not in best:
                best[key] = (source, item)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]
    out: list[dict[str, Any]] = []
    for rank, (key, rrf_score) in enumerate(ordered, start=1):
        source, item = best[key]
        out.append(_item_to_fused(source, item, rrf_score, rank))
    return out


def build_fused_ranking(bundle: dict[str, Any], *, limit: int = 25) -> list[dict[str, Any]]:
    """Collect hits from a retrieve_context bundle and return RRF-ordered list."""
    lists: list[tuple[str, list[dict[str, Any]]]] = []

    grep = bundle.get("code_grep")
    if isinstance(grep, dict) and grep.get("ok"):
        lists.append(("code_grep", list(grep.get("matches") or [])))

    sem = bundle.get("code_semantic")
    if isinstance(sem, dict) and sem.get("ok"):
        lists.append(("code_semantic", list(sem.get("results") or [])))

    docs = bundle.get("docs")
    if isinstance(docs, dict) and docs.get("ok"):
        lists.append(("docs", list(docs.get("hits") or [])))

    mem = bundle.get("memory")
    if isinstance(mem, dict) and mem.get("ok"):
        lists.append(("memory", list(mem.get("notes") or [])))

    if not lists:
        return []
    return reciprocal_rank_fusion(lists, limit=limit)
