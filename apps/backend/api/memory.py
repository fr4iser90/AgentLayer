"""User memory: structured facts + semantic notes (pgvector) + optional graph (nodes/edges).

Facts are authoritative key/value JSON (opt-in writes).
Notes are free-form and retrieved semantically via ``EMBEDDING_BASE_URL`` (see ``embedding_client``).
The graph layer stores compact nodes and relations; activation uses **semantic** (embedding) + keyword
match on label/summary, then expands 1 hop along edges.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

from apps.backend.api.rag import embed_one
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db

_SECRET_RE = re.compile(
    r"(?:\bapi[\s_-]*key\b|\btoken\b|\bpassword\b|\bsecret\b|-----BEGIN|sk-[A-Za-z0-9]{10,})",
    re.IGNORECASE,
)


def _enabled() -> bool:
    return bool(operator_settings.memory_service_enabled())


def _memory_graph_enabled() -> bool:
    return _enabled() and bool(operator_settings.memory_graph_prompt_settings()["enabled"])


def _tokenize_query_for_graph(q: str) -> list[str]:
    return list(
        dict.fromkeys(
            m.group(0).lower()
            for m in re.finditer(r"[a-z0-9äöüß]{2,}", (q or "").lower())
        )
    )[:32]


def _require_identity() -> tuple[int, uuid.UUID]:
    tid, uid = get_identity()
    if uid is None:
        raise ValueError("No user identity")
    return tid, uid


def _reject_secrets(text: str) -> None:
    if _SECRET_RE.search(text or ""):
        raise ValueError("refusing to store secrets (token/password/key-like content detected)")


def fact_upsert_for_identity(
    *,
    key: str,
    value_json: Any,
    dashboard_id: uuid.UUID | None = None,
    confidence: float | None = None,
    source: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    if not _enabled():
        raise ValueError("memory is disabled on this server")
    _require_identity()
    if isinstance(value_json, str):
        _reject_secrets(value_json)
    return db.memory_fact_upsert(
        key=key,
        value_json=value_json,
        dashboard_id=dashboard_id,
        confidence=confidence,
        source=source,
        expires_at=expires_at,
    )


def fact_list_for_identity(
    *,
    dashboard_id: uuid.UUID | None = None,
    prefix: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not _enabled():
        return []
    _require_identity()
    return db.memory_fact_list(dashboard_id=dashboard_id, prefix=prefix, limit=limit)


def fact_delete_for_identity(*, key: str, dashboard_id: uuid.UUID | None = None) -> bool:
    if not _enabled():
        raise ValueError("memory is disabled on this server")
    _require_identity()
    return db.memory_fact_delete(key=key, dashboard_id=dashboard_id)


def note_add_for_identity(
    *,
    text: str,
    dashboard_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    if not _enabled():
        raise ValueError("memory is disabled on this server")
    _require_identity()
    t = (text or "").strip()
    _reject_secrets(t)
    emb = embed_one(t)
    nid = db.memory_note_insert(text=t, embedding=emb, tags=tags, source=source, dashboard_id=dashboard_id)
    return {"ok": True, "id": nid}


def note_search_for_identity(
    *,
    query: str,
    dashboard_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not _enabled():
        return []
    _require_identity()
    q = (query or "").strip()
    if not q:
        return []
    emb = embed_one(q)
    return db.memory_note_vector_search(query_embedding=emb, dashboard_id=dashboard_id, tags=tags, limit=limit)


def note_delete_for_identity(*, note_id: int) -> bool:
    if not _enabled():
        raise ValueError("memory is disabled on this server")
    _require_identity()
    return db.memory_note_soft_delete(int(note_id))


def graph_node_add_for_identity(
    *,
    dashboard_id: uuid.UUID | None,
    kind: str,
    label: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    importance: float | None = None,
    confidence: float | None = None,
    source: str | None = None,
    last_verified: datetime | None = None,
    subject_key: str | None = None,
    stability: str | None = None,
    priority: float | None = None,
) -> dict[str, Any]:
    if not _memory_graph_enabled():
        raise ValueError("memory graph is disabled on this server")
    _require_identity()
    _reject_secrets((label or "") + " " + (summary or ""))
    lab = (label or "").strip()
    summ = (summary or "").strip()
    blurb = f"{lab}\n{summ}".strip() or lab
    emb: list[float] | None = None
    try:
        emb = embed_one(blurb[:12_000])
    except Exception:
        emb = None
    return db.memory_graph_node_insert(
        dashboard_id=dashboard_id,
        kind=kind,
        label=lab,
        summary=summ,
        payload=payload,
        importance=float(importance) if importance is not None else 1.0,
        embedding=emb,
        confidence=confidence,
        source=source,
        last_verified=last_verified,
        subject_key=subject_key,
        stability=stability,
        priority=priority,
    )


def graph_edge_add_for_identity(
    *,
    src_node_id: int,
    dst_node_id: int,
    rel_type: str = "related",
    weight: float = 1.0,
) -> dict[str, Any]:
    if not _memory_graph_enabled():
        raise ValueError("memory graph is disabled on this server")
    _require_identity()
    return db.memory_graph_edge_insert(
        src_node_id=int(src_node_id),
        dst_node_id=int(dst_node_id),
        rel_type=rel_type,
        weight=weight,
    )


def graph_nodes_list_for_identity(
    *,
    dashboard_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not _memory_graph_enabled():
        return []
    _require_identity()
    return db.memory_graph_list_nodes(dashboard_id=dashboard_id, limit=limit)


def graph_node_delete_for_identity(*, node_id: int) -> bool:
    if not _memory_graph_enabled():
        raise ValueError("memory graph is disabled on this server")
    _require_identity()
    return db.memory_graph_node_soft_delete(node_id=int(node_id))


def _maybe_log_graph_activation(
    dashboard_id: uuid.UUID | None,
    user_query: str,
    rows: list[dict[str, Any]],
) -> None:
    """Persist activated node ids + per-node scores for later RL / analytics (no raw query text)."""
    mg = operator_settings.memory_graph_prompt_settings()
    if not mg["log_activations"]:
        return
    if not rows:
        return
    try:
        from apps.backend.api.memory_graph_scoring import activation_score

        q = (user_query or "").strip().lower()
        qhash = hashlib.sha256(q.encode("utf-8")).hexdigest() if q else None
        scores = {str(int(r["id"])): round(float(activation_score(r)), 5) for r in rows}
        nids = [int(r["id"]) for r in rows]
        db.memory_graph_activation_log_insert(
            dashboard_id=dashboard_id,
            node_ids=nids,
            query_sha256=qhash,
            meta={
                "scores": scores,
                "max_hops": int(mg["max_hops"]),
                "node_count": len(nids),
            },
        )
    except Exception as e:
        logger.debug("memory graph activation log skipped: %s", e)


def graph_render_for_identity(
    *,
    dashboard_id: uuid.UUID | None,
    user_query: str,
    max_nodes: int = 12,
) -> str:
    """Compact bullet list for system prompt injection (decay/conflict-aware)."""
    if not _memory_graph_enabled():
        return ""
    _require_identity()
    from apps.backend.api.memory_graph_scoring import build_graph_prompt_section, rank_and_filter_nodes

    mg = operator_settings.memory_graph_prompt_settings()
    tokens = _tokenize_query_for_graph(user_query)
    qemb: list[float] | None = None
    raw_q = (user_query or "").strip()
    if raw_q:
        try:
            qemb = embed_one(raw_q[:12_000])
        except Exception:
            qemb = None
    hops = int(mg["max_hops"])
    hops = max(0, min(hops, 4))
    rows = db.memory_graph_activate(
        dashboard_id=dashboard_id,
        tokens=tokens,
        query_embedding=qemb,
        vec_seed_limit=8,
        keyword_seed_limit=6,
        max_nodes=max_nodes,
        max_hops=hops,
    )
    rows = rank_and_filter_nodes(rows)
    _maybe_log_graph_activation(dashboard_id, user_query, rows)
    return build_graph_prompt_section(rows)


def graph_stats_for_identity() -> dict[str, Any]:
    if not _memory_graph_enabled():
        return {}
    _require_identity()
    return db.memory_graph_stats()


def graph_activation_log_for_identity(*, limit: int = 100) -> list[dict[str, Any]]:
    if not _memory_graph_enabled():
        return []
    _require_identity()
    return db.memory_graph_activation_log_list(limit=limit)


def graph_propose_from_text_for_identity(
    *,
    text: str,
    dashboard_id: uuid.UUID | None,
    apply: bool,
) -> dict[str, Any]:
    if not _memory_graph_enabled():
        raise ValueError("memory graph is disabled on this server")
    _require_identity()
    from apps.backend.api.memory_graph_extract import propose_graph_from_text

    return propose_graph_from_text(text=text, dashboard_id=dashboard_id, apply=apply)


def render_memory_context(
    *,
    dashboard_id: uuid.UUID | None,
    user_query: str,
    facts_limit: int = 40,
    notes_limit: int = 6,
) -> str:
    """Build a compact system snippet. Caller decides where to inject it."""
    if not _enabled():
        return ""
    facts_global = fact_list_for_identity(dashboard_id=None, limit=facts_limit)
    facts_ws = fact_list_for_identity(dashboard_id=dashboard_id, limit=facts_limit) if dashboard_id else []
    merged: dict[str, dict[str, Any]] = {str(f["key"]): f for f in facts_global}
    for f in facts_ws:
        merged[str(f["key"])] = f
    notes = note_search_for_identity(query=user_query, dashboard_id=dashboard_id, limit=notes_limit)
    graph_snip = graph_render_for_identity(dashboard_id=dashboard_id, user_query=user_query)

    if not merged and not notes and not graph_snip:
        return ""

    lines: list[str] = []
    lines.append("[User memory — facts]")
    if merged:
        for k in sorted(merged.keys()):
            v = merged[k].get("value_json")
            lines.append(f"- {k}: {v!r}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("[User memory — notes]")
    if notes:
        for i, n in enumerate(notes[:notes_limit], 1):
            txt = str(n.get("text") or "").strip().replace("\n", " ")
            if len(txt) > 280:
                txt = txt[:280] + "…"
            tag_s = n.get("tags") or []
            tag_str = ", ".join(tag_s) if isinstance(tag_s, list) and tag_s else ""
            lines.append(f"{i}) {txt}" + (f" (tags: {tag_str})" if tag_str else ""))
    else:
        lines.append("(none)")
    out = "\n".join(lines).strip()
    if graph_snip:
        out = out + "\n\n" + graph_snip
    return out

