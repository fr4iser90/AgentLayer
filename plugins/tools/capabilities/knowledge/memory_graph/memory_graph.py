"""Graph memory tools: structured nodes + edges (FMA-style MVP). Opt-in writes."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.api import memory as memory_api

__version__ = "1.0.0"
TOOL_ID = "memory_graph"
TOOL_BUCKET = "knowledge"
TOOL_DOMAIN = "memory"
TOOL_LABEL = "Memory graph"
TOOL_DESCRIPTION = (
    "Structured graph memory: compact nodes (events, entities, tasks) and edges between them. "
    "Use only when the user explicitly asks to remember/link structured state for long-horizon context."
)
TOOL_TRIGGERS = (
    "graph memory",
    "memory graph",
    "knoten",
    "relation",
    "verknüpf",
    "entity",
    "kontext graph",
)
TOOL_CAPABILITIES = ("knowledge.memory_graph",)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _parse_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except ValueError:
        return None


def memory_graph_node_add(arguments: dict[str, Any]) -> str:
    label = (arguments.get("label") or "").strip()
    if not label:
        return _err("label is required")
    summary = str(arguments.get("summary") or "").strip()
    kind = str(arguments.get("kind") or "event").strip() or "event"
    wid = _parse_uuid(arguments.get("dashboard_id"))
    payload = arguments.get("payload")
    pl: dict[str, Any] | None = payload if isinstance(payload, dict) else None
    imp = arguments.get("importance")
    conf = arguments.get("confidence")
    src = arguments.get("source")
    sk = arguments.get("subject_key")
    stab = arguments.get("stability")
    prio = arguments.get("priority")
    try:
        row = memory_api.graph_node_add_for_identity(
            dashboard_id=wid,
            kind=kind,
            label=label,
            summary=summary,
            payload=pl,
            importance=float(imp) if imp is not None else None,
            confidence=float(conf) if conf is not None else None,
            source=str(src) if isinstance(src, str) else None,
            subject_key=str(sk) if isinstance(sk, str) else None,
            stability=str(stab) if isinstance(stab, str) else None,
            priority=float(prio) if prio is not None else None,
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "node": row}, ensure_ascii=False)


def memory_graph_edge_add(arguments: dict[str, Any]) -> str:
    try:
        src = int(arguments.get("src_node_id"))
        dst = int(arguments.get("dst_node_id"))
    except (TypeError, ValueError):
        return _err("src_node_id and dst_node_id must be integers")
    rel = str(arguments.get("rel_type") or "related").strip() or "related"
    try:
        w = float(arguments.get("weight") or 1.0)
    except (TypeError, ValueError):
        w = 1.0
    try:
        row = memory_api.graph_edge_add_for_identity(
            src_node_id=src,
            dst_node_id=dst,
            rel_type=rel,
            weight=w,
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "edge": row}, ensure_ascii=False)


def memory_graph_nodes_list(arguments: dict[str, Any]) -> str:
    wid = _parse_uuid(arguments.get("dashboard_id"))
    try:
        lim = int(arguments.get("limit") or 80)
    except (TypeError, ValueError):
        lim = 80
    try:
        rows = memory_api.graph_nodes_list_for_identity(dashboard_id=wid, limit=lim)
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "nodes": rows, "count": len(rows)}, ensure_ascii=False)


def memory_graph_propose(arguments: dict[str, Any]) -> str:
    text = (arguments.get("text") or "").strip()
    if not text:
        return _err("text is required")
    wid = _parse_uuid(arguments.get("dashboard_id"))
    apply_raw = arguments.get("apply")
    apply = bool(apply_raw) if apply_raw is not None else False
    try:
        out = memory_api.graph_propose_from_text_for_identity(
            text=text, dashboard_id=wid, apply=apply
        )
    except Exception as e:
        return _err(str(e))
    return json.dumps(out, ensure_ascii=False)


def memory_graph_node_delete(arguments: dict[str, Any]) -> str:
    try:
        nid = int(arguments.get("node_id"))
    except (TypeError, ValueError):
        return _err("node_id must be an integer")
    try:
        ok = memory_api.graph_node_delete_for_identity(node_id=nid)
    except Exception as e:
        return _err(str(e))
    return json.dumps({"ok": True, "deleted": bool(ok)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "memory_graph_node_add": memory_graph_node_add,
    "memory_graph_edge_add": memory_graph_edge_add,
    "memory_graph_nodes_list": memory_graph_nodes_list,
    "memory_graph_propose": memory_graph_propose,
    "memory_graph_node_delete": memory_graph_node_delete,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_graph_node_add",
            "TOOL_DESCRIPTION": "Add one graph memory node (short label + summary). Only on explicit user request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "kind": {"type": "string", "TOOL_DESCRIPTION": "e.g. event, entity, task"},
                    "label": {"type": "string"},
                    "summary": {"type": "string"},
                    "payload": {"type": "object"},
                    "importance": {"type": "number"},
                    "confidence": {"type": "number"},
                    "source": {"type": "string"},
                    "subject_key": {"type": "string"},
                    "stability": {"type": "string", "TOOL_DESCRIPTION": "volatile, normal, or stable"},
                    "priority": {"type": "number"},
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_graph_propose",
            "TOOL_DESCRIPTION": "Propose graph nodes/edges from free text via local LLM; set apply=true to persist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "dashboard_id": {"type": "string"},
                    "apply": {"type": "boolean"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_graph_edge_add",
            "TOOL_DESCRIPTION": "Link two existing graph nodes (same user).",
            "parameters": {
                "type": "object",
                "properties": {
                    "src_node_id": {"type": "integer"},
                    "dst_node_id": {"type": "integer"},
                    "rel_type": {"type": "string"},
                    "weight": {"type": "number"},
                },
                "required": ["src_node_id", "dst_node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_graph_nodes_list",
            "TOOL_DESCRIPTION": "List this user's graph memory nodes (most recent first).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_graph_node_delete",
            "TOOL_DESCRIPTION": "Soft-delete one graph node by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                },
                "required": ["node_id"],
            },
        },
    },
]
