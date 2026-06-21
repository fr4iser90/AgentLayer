"""K1-lite workspace knowledge graph tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

try:
    from apps.backend.infrastructure.code_graph_neo4j import get_code_graph
    from apps.backend.infrastructure.workspace_k1_lite import build_workspace_knowledge_units

    _HAS_K1 = True
except ImportError:
    _HAS_K1 = False

__version__ = "1.0.0"
TOOL_ID = "knowledge"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "repository"
TOOL_CAPABILITIES = ("knowledge.retrieve", "coding.read")
TOOL_LABEL = "Workspace: K1-lite knowledge"
TOOL_DESCRIPTION = (
    "Build/query a K1-lite project knowledge graph from workspace docs and code. "
    "This is separate from project RAG: it stores structured entities, claims, and evidence in Neo4j."
)


def _workspace_or_error(context: dict | None) -> tuple[dict[str, Any] | None, str | None]:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return None, json_workspace_missing_error()
    return ws, None


def knowledge_index(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not _HAS_K1:
        return json.dumps({"ok": False, "error": "K1-lite dependencies are unavailable"}, ensure_ascii=False)
    ws, err = _workspace_or_error(context)
    if err:
        return err
    assert ws is not None
    if ws.get("graph_index_enabled") is False:
        return json.dumps({"ok": False, "skipped": True, "reason": "graph_index_disabled"}, ensure_ascii=False)

    graph = get_code_graph()
    if not graph.available():
        return json.dumps({"ok": False, "error": "Neo4j is not reachable or not configured (NEO4J_URL)."}, ensure_ascii=False)

    root = Path(str(ws["path"]))
    workspace_id = str(ws.get("id") or "")
    max_files = max(10, min(int(arguments.get("max_files") or 1000), 20000))
    try:
        from apps.backend.domain.identity import get_identity
        from apps.backend.infrastructure import agent_config_effective
        from apps.backend.infrastructure.extractor_catalog_providers import get_extractor_provider_spec

        tenant_id, _user_id = get_identity()
        cfg_tid = int(tenant_id) if tenant_id is not None else None
        extractor_backend = agent_config_effective.knowledge_extractor_backend(tenant_id=cfg_tid)
        extractor_provider_id = agent_config_effective.knowledge_extractor_provider_id(tenant_id=cfg_tid)
        extractor_model = agent_config_effective.knowledge_extractor_model(tenant_id=cfg_tid)
        extractor_provider = get_extractor_provider_spec(extractor_provider_id)
        if extractor_backend == "llm" and extractor_provider is None:
            return json.dumps(
                {
                    "ok": False,
                    "error": "knowledge.extractor_backend=llm but no EXTRACTOR_PROVIDER_N_* is configured.",
                    "note": "Use deterministic or hybrid, or configure EXTRACTOR_PROVIDER_1_BASE_URL and model.",
                },
                ensure_ascii=False,
            )
        if extractor_backend == "llm" and not (extractor_model or (extractor_provider and extractor_provider.model_default)):
            return json.dumps(
                {
                    "ok": False,
                    "error": "knowledge.extractor_backend=llm but no extractor model is configured.",
                    "note": "Set knowledge.extractor_model or EXTRACTOR_PROVIDER_N_MODEL.",
                },
                ensure_ascii=False,
            )
    except Exception:
        extractor_backend = "deterministic"
        extractor_provider_id = None
        extractor_model = None
        extractor_provider = None

    extracted = build_workspace_knowledge_units(
        root,
        max_files=max_files,
        extractor_backend=extractor_backend,
        extractor_provider_id=extractor_provider_id,
        extractor_model=extractor_model,
    )
    units_written = 0
    files_written = 0
    for rel_path, units in extracted:
        written = graph.replace_file_knowledge_units(workspace_id, rel_path, units)
        if written:
            files_written += 1
            units_written += written
    return json.dumps(
        {
            "ok": True,
            "workspace_id": workspace_id,
            "files_with_units": files_written,
            "knowledge_units": units_written,
            "schema": "k1_lite_v1",
            "kinds": ["entity", "claim", "evidence"],
            "extractor_backend": extractor_backend,
            "extractor_provider_id": extractor_provider.provider_id if extractor_provider is not None else None,
            "extractor_model": extractor_model or (extractor_provider.model_default if extractor_provider is not None else None),
            "note": "Project RAG settings were not changed.",
        },
        ensure_ascii=False,
    )


def knowledge_query(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not _HAS_K1:
        return json.dumps({"ok": False, "error": "K1-lite dependencies are unavailable"}, ensure_ascii=False)
    ws, err = _workspace_or_error(context)
    if err:
        return err
    assert ws is not None
    if ws.get("graph_index_enabled") is False:
        return json.dumps({"ok": False, "skipped": True, "reason": "graph_index_disabled"}, ensure_ascii=False)

    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False)
    raw_kinds = arguments.get("kinds")
    kinds = [str(x).strip().lower() for x in raw_kinds] if isinstance(raw_kinds, list) else []
    limit = max(1, min(int(arguments.get("limit") or 10), 50))

    graph = get_code_graph()
    if not graph.available():
        return json.dumps({"ok": False, "error": "Neo4j is not reachable or not configured (NEO4J_URL)."}, ensure_ascii=False)

    results = graph.query_knowledge_units(
        str(ws.get("id") or ""),
        query,
        kinds=kinds,
        limit=limit,
    )
    return json.dumps(
        {
            "ok": True,
            "query": query,
            "results": results,
            "count": len(results),
            "hint": "Use read_file on result file_path:line to verify evidence before editing or answering.",
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "knowledge_index": knowledge_index,
    "knowledge_query": knowledge_query,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_index",
            "description": (
                "Build/refresh K1-lite structured project knowledge for the bound workspace. "
                "Extracts entities, claims, and evidence from docs/code into Neo4j. Does not alter project RAG."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum workspace files to scan (default 1000).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_query",
            "description": (
                "Query K1-lite structured project knowledge in Neo4j for entities, claims, and evidence. "
                "Use this for evidence-oriented exploration before editing or answering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question, entity, symbol, or concept to find."},
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["entity", "claim", "evidence"]},
                        "description": "Optional unit kinds to search.",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10, max 50)."},
                },
                "required": ["query"],
            },
        },
    },
]

