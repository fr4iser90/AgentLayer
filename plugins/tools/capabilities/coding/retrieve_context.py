"""Unified retrieval for coding agents: grep + semantic code + optional RAG docs + memory notes."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from apps.backend.infrastructure import operator_settings

from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
    workspace_docs_rag_enabled,
    workspace_id_from_context,
    workspace_retrieval_flags,
)
from plugins.tools.capabilities.coding.coding_search import coding_search
from plugins.tools.capabilities.coding.coding_semantic_search import coding_semantic_search
from plugins.tools.capabilities.coding.retrieval_fusion import build_fused_ranking

__version__ = "1.0.0"
TOOL_ID = "retrieve_context"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = (
    "retrieve",
    "context",
    "semantic search",
    "find in codebase",
    "search docs and code",
    "rag",
)
TOOL_CAPABILITIES = ("coding.read", "knowledge.retrieve")
TOOL_LABEL = "Retrieve context"
TOOL_DESCRIPTION = (
    "One-shot retrieval across the workspace and knowledge bases: "
    "keyword grep (coding_search), semantic symbols (Qdrant, needs coding_index), "
    "ingested docs (RAG), and optional semantic memory notes. "
    "Results are merged with RRF (fused_ranking). "
    "Prefer this before many separate search tools — then use coding_read_file on cited path:line."
)

_VALID_SOURCES = frozenset({"code_grep", "code_semantic", "docs", "memory"})
_DEFAULT_SOURCES = ("code_grep", "code_semantic", "docs")
_MAX_WORKERS = 4


def _parse_sources(raw: Any) -> list[str]:
    if raw is None:
        return list(_DEFAULT_SOURCES)
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(",", " ").split() if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        return list(_DEFAULT_SOURCES)
    out = [p for p in parts if p in _VALID_SOURCES]
    return out or list(_DEFAULT_SOURCES)


def _clamp_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _json_loads_safe(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid json from sub-retriever"}
    if isinstance(data, dict):
        return data
    return {"ok": False, "error": "sub-retriever did not return an object"}


def _run_code_grep(query: str, context: dict[str, Any] | None, limit: int) -> dict[str, Any]:
    from apps.backend.core.config import config as cfg

    cap = min(limit, int(cfg.WORKSPACE_MAX_SEARCH_MATCHES))
    raw = coding_search({"query": query, "regex": False}, context=context)
    data = _json_loads_safe(raw)
    if not data.get("ok"):
        return data
    matches = data.get("matches")
    if isinstance(matches, list) and len(matches) > cap:
        data = {**data, "matches": matches[:cap], "truncated_matches": True}
    return data


def _run_code_semantic(query: str, context: dict[str, Any] | None, limit: int) -> dict[str, Any]:
    raw = coding_semantic_search({"query": query, "limit": limit}, context=context)
    return _json_loads_safe(raw)


def _run_docs(
    query: str,
    limit: int,
    *,
    context: dict[str, Any] | None,
    domain: str | None,
) -> dict[str, Any]:
    rs = operator_settings.rag_settings()
    if not rs["enabled"]:
        return {"ok": False, "skipped": True, "reason": "rag_disabled"}

    wid_raw = workspace_id_from_context(context)
    if wid_raw:
        if not workspace_docs_rag_enabled(context):
            return {"ok": False, "skipped": True, "reason": "docs_rag_disabled"}
        try:
            ws_uuid = uuid.UUID(wid_raw)
        except ValueError:
            return {"ok": False, "error": "invalid workspace id in context"}
        try:
            from apps.backend.infrastructure.rag import rag as rag_service

            rows = rag_service.search_for_identity(query, limit=limit, workspace_id=ws_uuid)
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
        scope = "workspace"
        dom = "workspace_docs"
    else:
        dom = (domain or "agentlayer_docs").strip() or "agentlayer_docs"
        try:
            from apps.backend.infrastructure.rag import rag as rag_service

            rows = rag_service.search_for_identity(query, domain=dom, limit=limit)
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
        scope = "global"

    hits = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        dist = row.get("distance")
        hits.append(
            {
                "domain": row.get("domain"),
                "title": row.get("title"),
                "source_uri": row.get("source_uri"),
                "chunk_index": row.get("chunk_index"),
                "distance": dist,
                "text": (row.get("content") or "")[:2000],
            }
        )
    if scope == "workspace" and not hits:
        return {
            "ok": True,
            "scope": scope,
            "workspace_id": wid_raw,
            "domain": dom,
            "hits": [],
            "count": 0,
            "hint": "No workspace docs indexed yet — run Reindex with Docs RAG enabled.",
        }
    return {
        "ok": True,
        "scope": scope,
        "workspace_id": wid_raw if scope == "workspace" else None,
        "domain": dom,
        "hits": hits,
        "count": len(hits),
    }


def _run_memory(query: str, limit: int) -> dict[str, Any]:
    if not operator_settings.memory_service_enabled():
        return {"ok": False, "skipped": True, "reason": "memory_disabled"}
    try:
        from apps.backend.api.memory import note_search_for_identity

        notes = note_search_for_identity(query=query, dashboard_id=None, limit=limit)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    slim = []
    for n in notes[:limit]:
        if not isinstance(n, dict):
            continue
        slim.append(
            {
                "id": n.get("id"),
                "score": n.get("score"),
                "text": (n.get("text") or "")[:1500],
                "tags": n.get("tags"),
            }
        )
    return {"ok": True, "notes": slim, "count": len(slim)}


def _skipped(source: str, reason: str) -> dict[str, Any]:
    return {"skipped": True, "reason": reason, "source": source}


def _retriever_tasks(
    sources: list[str],
    *,
    query: str,
    context: dict[str, Any] | None,
    domain: str,
    sem_on: bool,
    grep_limit: int,
    semantic_limit: int,
    docs_limit: int,
    memory_limit: int,
) -> list[tuple[str, Callable[[], dict[str, Any]]]]:
    tasks: list[tuple[str, Callable[[], dict[str, Any]]]] = []
    if "code_grep" in sources:
        tasks.append(("code_grep", lambda: _run_code_grep(query, context, grep_limit)))
    if "code_semantic" in sources:
        if sem_on:
            tasks.append(("code_semantic", lambda: _run_code_semantic(query, context, semantic_limit)))
    if "docs" in sources:
        tasks.append(
            ("docs", lambda: _run_docs(query, docs_limit, context=context, domain=domain))
        )
    if "memory" in sources:
        tasks.append(("memory", lambda: _run_memory(query, memory_limit)))
    return tasks


def _run_retrievers_parallel(tasks: list[tuple[str, Callable[[], dict[str, Any]]]]) -> dict[str, Any]:
    if not tasks:
        return {}
    if len(tasks) == 1:
        name, fn = tasks[0]
        return {name: fn()}

    out: dict[str, Any] = {}
    workers = min(_MAX_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                out[name] = fut.result()
            except Exception as e:
                out[name] = {"ok": False, "error": str(e)[:300]}
    return out


def _next_steps(bundle: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    fused = bundle.get("fused_ranking")
    if isinstance(fused, list) and fused:
        top = fused[0]
        if isinstance(top, dict):
            src = top.get("source")
            path = top.get("path")
            line = top.get("line", 1)
            if path and src in ("code_grep", "code_semantic"):
                label = top.get("name") or "top fused match"
                steps.append(f"Read `coding_read_file` on {path}:{line} ({label}, source={src}).")
            elif src == "docs" and top.get("title"):
                steps.append(f"Open doc chunk «{top.get('title')}» (fused top hit).")
            elif src == "memory" and top.get("text"):
                steps.append("Review fused memory note in the top hit.")

    if not steps:
        grep = bundle.get("code_grep")
        if isinstance(grep, dict) and grep.get("ok") and grep.get("matches"):
            m0 = grep["matches"][0]
            if isinstance(m0, dict) and m0.get("path"):
                steps.append(
                    f"Read `coding_read_file` on {m0.get('path')}:{m0.get('line', 1)} for the top grep hit."
                )
        sem = bundle.get("code_semantic")
        if isinstance(sem, dict) and sem.get("ok") and sem.get("results"):
            r0 = sem["results"][0]
            if isinstance(r0, dict) and r0.get("file_path"):
                steps.append(
                    f"Open semantic match {r0.get('file_path')}:{r0.get('line', 1)} "
                    f"({r0.get('name', '')})."
                )

    if not steps:
        steps.append("Narrow the query or run `coding_index` then retry `retrieve_context`.")
    steps.append("Use `coding_lsp` for definitions/refs after you have a file path.")
    return steps


def retrieve_context(arguments: dict[str, Any], context: dict | None = None) -> str:
    query = (arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False)

    sources = _parse_sources(arguments.get("sources"))
    domain = str(arguments.get("domain") or "agentlayer_docs").strip()
    grep_limit = _clamp_int(arguments.get("grep_limit"), 25, 1, 50)
    semantic_limit = _clamp_int(arguments.get("semantic_limit"), 12, 1, 50)
    docs_limit = _clamp_int(arguments.get("docs_limit"), 6, 1, 30)
    memory_limit = _clamp_int(arguments.get("memory_limit"), 4, 1, 20)
    fused_limit = _clamp_int(arguments.get("fused_limit"), 25, 1, 50)

    needs_workspace = "code_grep" in sources or "code_semantic" in sources
    if needs_workspace and workspace_binding_from_context(context) is None:
        return json_workspace_missing_error()

    sem_on, ret_on = workspace_retrieval_flags(context)
    if not ret_on:
        return json.dumps(
            {
                "ok": False,
                "skipped": True,
                "reason": "retrieval_disabled",
                "hint": "Enable the retrieval layer on this workspace in the Coding Agent header.",
            },
            ensure_ascii=False,
        )

    tasks = _retriever_tasks(
        sources,
        query=query,
        context=context,
        domain=domain,
        sem_on=sem_on,
        grep_limit=grep_limit,
        semantic_limit=semantic_limit,
        docs_limit=docs_limit,
        memory_limit=memory_limit,
    )
    parallel = _run_retrievers_parallel(tasks)

    out: dict[str, Any] = {
        "ok": True,
        "query": query,
        "sources_requested": sources,
    }

    if "code_grep" in sources:
        out["code_grep"] = parallel.get("code_grep") or _skipped("code_grep", "not_run")
    else:
        out["code_grep"] = _skipped("code_grep", "not_requested")

    if "code_semantic" in sources:
        if sem_on:
            out["code_semantic"] = parallel.get("code_semantic") or _skipped("code_semantic", "not_run")
        else:
            out["code_semantic"] = _skipped("code_semantic", "semantic_index_disabled")
    else:
        out["code_semantic"] = _skipped("code_semantic", "not_requested")

    if "docs" in sources:
        out["docs"] = parallel.get("docs") or _skipped("docs", "not_run")
    else:
        out["docs"] = _skipped("docs", "not_requested")

    if "memory" in sources:
        out["memory"] = parallel.get("memory") or _skipped("memory", "not_run")
    else:
        out["memory"] = _skipped("memory", "not_requested")

    out["fused_ranking"] = build_fused_ranking(out, limit=fused_limit)
    out["next_steps"] = _next_steps(out)
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[..., str]] = {
    "retrieve_context": retrieve_context,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_context",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to find (natural language or keywords).",
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["code_grep", "code_semantic", "docs", "memory"],
                        },
                        "description": (
                            "Retrievers to run (default: code_grep, code_semantic, docs). "
                            "Add memory for user notes."
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "RAG domain when no workspace is bound (default agentlayer_docs). "
                            "Ignored when a workspace is active — only that workspace's indexed *.md is searched."
                        ),
                    },
                    "grep_limit": {"type": "integer", "description": "Max grep hits (1–50)."},
                    "semantic_limit": {
                        "type": "integer",
                        "description": "Max Qdrant symbol hits (1–50).",
                    },
                    "docs_limit": {"type": "integer", "description": "Max RAG chunks (1–30)."},
                    "memory_limit": {
                        "type": "integer",
                        "description": "Max memory notes (1–20).",
                    },
                    "fused_limit": {
                        "type": "integer",
                        "description": "Max RRF fused hits (1–50).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
