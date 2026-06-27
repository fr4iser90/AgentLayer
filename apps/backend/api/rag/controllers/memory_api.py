"""HTTP API for user memory (facts + semantic notes + optional graph nodes/edges).

This is a user-facing wrapper around the same storage used by the `memory_*` and `memory_graph_*` tools.
All operations are scoped to the authenticated chat identity (tenant_id + user_id).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.application.rag.use_cases.rag_controller_services import memory_service

router = APIRouter(prefix="/v1/user/memory", tags=["user-memory"])


@contextmanager
def _memory_request_identity(request: Request) -> Iterator[None]:
    """Bind chat identity for memory_service (uses ``get_identity()`` internally)."""
    uid, tid = resolve_chat_identity(request)
    token = set_identity(tid, uid)
    try:
        yield
    finally:
        reset_identity(token)


def _parse_uuid(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="dashboard_id must be UUID") from None


class FactUpsertBody(BaseModel):
    dashboard_id: str | None = None
    key: str = Field(min_length=1, max_length=256)
    value_json: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = Field(default=None, max_length=256)
    expires_at: str | None = None


@router.post("/facts/upsert")
def upsert_fact(request: Request, body: FactUpsertBody) -> dict:
    wid = _parse_uuid(body.dashboard_id)
    exp: datetime | None = None
    if body.expires_at and body.expires_at.strip():
        try:
            exp = datetime.fromisoformat(body.expires_at.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="expires_at must be ISO timestamp") from e
    try:
        with _memory_request_identity(request):
            fact = memory_service.fact_upsert_for_identity(
                key=body.key,
                value_json=body.value_json,
                dashboard_id=wid,
                confidence=body.confidence,
                source=body.source,
                expires_at=exp,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "fact": fact}


@router.get("/facts")
def list_facts(request: Request, dashboard_id: str | None = None, prefix: str | None = None, limit: int = 50) -> dict:
    wid = _parse_uuid(dashboard_id)
    try:
        with _memory_request_identity(request):
            facts = memory_service.fact_list_for_identity(dashboard_id=wid, prefix=prefix, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "facts": facts, "count": len(facts)}


@router.delete("/facts/{key}")
def delete_fact(request: Request, key: str, dashboard_id: str | None = None) -> dict:
    wid = _parse_uuid(dashboard_id)
    try:
        with _memory_request_identity(request):
            ok = memory_service.fact_delete_for_identity(key=key, dashboard_id=wid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "deleted": bool(ok)}


class NoteAddBody(BaseModel):
    dashboard_id: str | None = None
    text: str = Field(min_length=1, max_length=20_000)
    tags: list[str] | None = None
    source: str | None = Field(default=None, max_length=256)


@router.post("/notes")
def add_note(request: Request, body: NoteAddBody) -> dict:
    wid = _parse_uuid(body.dashboard_id)
    try:
        with _memory_request_identity(request):
            out = memory_service.note_add_for_identity(
                text=body.text,
                dashboard_id=wid,
                tags=body.tags,
                source=body.source,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, **out}


@router.get("/notes/search")
def search_notes(
    request: Request,
    query: str,
    dashboard_id: str | None = None,
    limit: int = 10,
) -> dict:
    wid = _parse_uuid(dashboard_id)
    try:
        with _memory_request_identity(request):
            hits = memory_service.note_search_for_identity(query=query, dashboard_id=wid, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "hits": hits, "count": len(hits)}


@router.delete("/notes/{note_id}")
def delete_note(request: Request, note_id: int) -> dict:
    try:
        with _memory_request_identity(request):
            ok = memory_service.note_delete_for_identity(note_id=note_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "deleted": bool(ok)}


class GraphNodeBody(BaseModel):
    dashboard_id: str | None = None
    kind: str = Field(default="event", max_length=64)
    label: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=20_000)
    payload: dict[str, Any] | None = None
    importance: float | None = Field(default=None, ge=0.0, le=10.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = Field(default=None, max_length=256)
    last_verified: str | None = None
    subject_key: str | None = Field(default=None, max_length=512)
    stability: str | None = Field(default=None, max_length=16)
    priority: float | None = Field(default=None, ge=-50.0, le=50.0)


@router.post("/graph/nodes")
def graph_add_node(request: Request, body: GraphNodeBody) -> dict:
    wid = _parse_uuid(body.dashboard_id)
    lv: datetime | None = None
    if body.last_verified and body.last_verified.strip():
        try:
            lv = datetime.fromisoformat(body.last_verified.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail="last_verified must be ISO timestamp") from e
    try:
        with _memory_request_identity(request):
            row = memory_service.graph_node_add_for_identity(
            dashboard_id=wid,
            kind=body.kind,
            label=body.label,
            summary=body.summary,
            payload=body.payload,
            importance=body.importance,
            confidence=body.confidence,
            source=body.source,
            last_verified=lv,
            subject_key=body.subject_key,
            stability=body.stability,
            priority=body.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "node": row}


class GraphEdgeBody(BaseModel):
    src_node_id: int = Field(ge=1)
    dst_node_id: int = Field(ge=1)
    rel_type: str = Field(default="related", max_length=64)
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


@router.post("/graph/edges")
def graph_add_edge(request: Request, body: GraphEdgeBody) -> dict:
    try:
        with _memory_request_identity(request):
            row = memory_service.graph_edge_add_for_identity(
            src_node_id=body.src_node_id,
            dst_node_id=body.dst_node_id,
            rel_type=body.rel_type,
            weight=body.weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "edge": row}


@router.get("/graph/nodes")
def graph_list_nodes(request: Request, dashboard_id: str | None = None, limit: int = 100) -> dict:
    wid = _parse_uuid(dashboard_id)
    try:
        with _memory_request_identity(request):
            nodes = memory_service.graph_nodes_list_for_identity(dashboard_id=wid, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "nodes": nodes, "count": len(nodes)}


@router.delete("/graph/nodes/{node_id}")
def graph_delete_node(request: Request, node_id: int) -> dict:
    try:
        with _memory_request_identity(request):
            ok = memory_service.graph_node_delete_for_identity(node_id=node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "deleted": bool(ok)}


@router.get("/graph/stats")
def graph_stats(request: Request) -> dict:
    try:
        with _memory_request_identity(request):
            stats = memory_service.graph_stats_for_identity()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, **stats}


@router.get("/graph/activation-log")
def graph_activation_log(request: Request, limit: int = 100) -> dict:
    try:
        with _memory_request_identity(request):
            rows = memory_service.graph_activation_log_for_identity(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "events": rows, "count": len(rows)}


class GraphProposeBody(BaseModel):
    text: str = Field(min_length=1, max_length=48_000)
    dashboard_id: str | None = None
    apply: bool = False


@router.post("/graph/propose")
def graph_propose(request: Request, body: GraphProposeBody) -> dict:
    wid = _parse_uuid(body.dashboard_id)
    try:
        with _memory_request_identity(request):
            out = memory_service.graph_propose_from_text_for_identity(
            text=body.text,
            dashboard_id=wid,
            apply=body.apply,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return out

