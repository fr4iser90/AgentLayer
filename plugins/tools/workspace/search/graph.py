"""Code graph queries: call-graph, dependency-graph, type hierarchy, impact analysis via Neo4j."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.domain.coding.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

try:
    from apps.backend.infrastructure.code_graph_neo4j import get_code_graph
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False

__version__ = "1.0.0"
TOOL_ID = "graph"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "repository"
# Router phrases: co-located graph.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Graph"
TOOL_DESCRIPTION = (
    "Query the code graph (Neo4j) for structural relationships in the workspace. "
    "Operations: callers (who calls X?), callees (what does X call?), "
    "dependencies (what does file X import?), dependents (who imports file X?), "
    "hierarchy (sub/superclasses of X), impact (what is affected if X changes?). "
    "Requires prior indexing via coding_index."
)

_VALID_OPS = frozenset({"callers", "callees", "dependencies", "dependents", "hierarchy", "impact"})


def graph(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not _HAS_NEO4J:
        return json.dumps(
            {"ok": False, "error": "Neo4j driver not available. Install: pip install neo4j"},
            ensure_ascii=False,
        )

    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    if ws.get("graph_index_enabled") is False:
        return json.dumps(
            {"ok": False, "skipped": True, "reason": "graph_index_disabled"},
            ensure_ascii=False,
        )
    workspace_id = str(ws.get("id") or "")

    graph = get_code_graph()
    if not graph.available():
        return json.dumps(
            {"ok": False, "error": "Neo4j is not reachable or not configured (NEO4J_URL)."},
            ensure_ascii=False,
        )

    op = (arguments.get("operation") or "").strip().lower()
    if not op:
        return json.dumps(
            {
                "ok": True,
                "operation": "status",
                "available": True,
                "operations": sorted(_VALID_OPS),
                "hint": "Run coding_index first to populate the graph, then query with an operation.",
            },
            ensure_ascii=False,
        )

    if op not in _VALID_OPS:
        return json.dumps(
            {"ok": False, "error": f"operation must be one of {sorted(_VALID_OPS)}"},
            ensure_ascii=False,
        )

    name = (arguments.get("name") or "").strip()
    path = (arguments.get("path") or "").strip()
    transitive = bool(arguments.get("transitive", False))
    max_depth = max(1, min(int(arguments.get("max_depth", 5)), 15))

    if op == "callers":
        if not name:
            return _error("name is required for callers")
        results = graph.query_callers(workspace_id, name, transitive=transitive, max_depth=max_depth)
        return _result(op, results, query={"name": name, "transitive": transitive})

    if op == "callees":
        if not name:
            return _error("name is required for callees")
        results = graph.query_callees(workspace_id, name)
        return _result(op, results, query={"name": name})

    if op == "dependencies":
        if not path:
            return _error("path is required for dependencies")
        results = graph.query_dependencies(workspace_id, path, transitive=transitive, max_depth=max_depth)
        return _result(op, results, query={"path": path, "transitive": transitive})

    if op == "dependents":
        if not path:
            return _error("path is required for dependents")
        results = graph.query_dependents(workspace_id, path, transitive=transitive, max_depth=max_depth)
        return _result(op, results, query={"path": path, "transitive": transitive})

    if op == "hierarchy":
        if not name:
            return _error("name is required for hierarchy")
        direction = (arguments.get("direction") or "subclasses").strip().lower()
        if direction not in ("subclasses", "superclasses"):
            direction = "subclasses"
        results = graph.query_hierarchy(workspace_id, name, direction=direction, max_depth=max_depth)
        return _result(op, results, query={"name": name, "direction": direction})

    if op == "impact":
        if not name:
            return _error("name is required for impact")
        results = graph.query_impact(workspace_id, name, max_depth=max_depth)
        return _result(op, results, query={"name": name, "max_depth": max_depth})

    return _error("unreachable")


def _error(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _result(op: str, results: list[dict[str, Any]], query: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {
            "ok": True,
            "operation": op,
            "query": query or {},
            "results": results,
            "count": len(results),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "graph": graph,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "graph",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": sorted(_VALID_OPS),
                        "description": (
                            "callers: who calls symbol? | callees: what does symbol call? | "
                            "dependencies: what does file import? | dependents: who imports file? | "
                            "hierarchy: sub/superclasses | impact: what breaks if symbol changes?"
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Symbol name (function or class) for callers/callees/hierarchy/impact.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative file path for dependencies/dependents (e.g. apps/backend/api/rag.py).",
                    },
                    "transitive": {
                        "type": "boolean",
                        "description": "Follow edges transitively (default false). For callers/dependencies/dependents.",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max traversal depth for transitive queries (default 5, max 15).",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["subclasses", "superclasses"],
                        "description": "For hierarchy: subclasses (who extends X?) or superclasses (what does X extend?).",
                    },
                },
                "required": ["operation"],
            },
        },
    },
]
