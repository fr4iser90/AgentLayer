"""LLM-assisted extraction of proposed graph nodes/edges from free text (optional apply)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from apps.backend.api.rag import embed_one
from apps.backend.infrastructure.catalog_llm_client import post_catalog_chat_completions

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """You extract structured memory graph nodes for a personal assistant.
Return ONLY valid JSON (no markdown fences) with this shape:
{
  "nodes": [
    {
      "kind": "event|entity|task|goal",
      "label": "short title",
      "summary": "one or two sentences",
      "subject_key": "optional stable key for conflict detection e.g. server:traefik:443",
      "stability": "volatile|normal|stable",
      "priority": 0,
      "confidence": 0.85
    }
  ],
  "edges": [
    {"src": 0, "dst": 1, "rel_type": "related"}
  ]
}
Use 0-based indices into "nodes" for edges. If no edges, use "edges": [].
Do not invent secrets. Keep nodes under 12 unless the text clearly needs more."""


def propose_graph_from_text(
    *,
    text: str,
    dashboard_id: uuid.UUID | None,
    apply: bool,
) -> dict[str, Any]:
    """
    Call catalog LLM chat to propose nodes/edges. If ``apply``, insert nodes (with embeddings) and edges.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("text is required")
    if len(raw) > 48_000:
        raw = raw[:48_000]

    data, _ = post_catalog_chat_completions(
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": raw},
        ],
        timeout=120.0,
        temperature=0.1,
    )
    choice0 = (data.get("choices") or [{}])[0]
    msg = (choice0.get("message") or {}) if isinstance(choice0, dict) else {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("model returned empty content")

    js = _parse_json_loose(content)
    if not isinstance(js, dict):
        raise ValueError("model did not return a JSON object")
    nodes_raw = js.get("nodes")
    edges_raw = js.get("edges")
    if not isinstance(nodes_raw, list):
        nodes_raw = []
    if not isinstance(edges_raw, list):
        edges_raw = []

    proposal: dict[str, Any] = {"nodes": nodes_raw, "edges": edges_raw}
    if not apply:
        return {"ok": True, "proposal": proposal, "applied": False}

    id_by_index: list[int | None] = [None] * len(nodes_raw)
    for i, n in enumerate(nodes_raw):
        if not isinstance(n, dict):
            continue
        kind = str(n.get("kind") or "event").strip() or "event"
        label = str(n.get("label") or "").strip()
        summary = str(n.get("summary") or "").strip()
        if not label:
            continue
        sk = str(n.get("subject_key") or "").strip() or None
        stab = str(n.get("stability") or "normal").strip().lower() or "normal"
        if stab not in ("volatile", "normal", "stable"):
            stab = "normal"
        try:
            prio = float(n.get("priority") or 0.0)
        except (TypeError, ValueError):
            prio = 0.0
        try:
            conf_f = float(n.get("confidence") or 0.85)
        except (TypeError, ValueError):
            conf_f = 0.85
        conf_f = max(0.0, min(1.0, conf_f))
        blurb = f"{label}\n{summary}".strip() or label
        emb: list[float] | None = None
        try:
            emb = embed_one(blurb[:12_000])
        except Exception as e:
            logger.warning("graph propose: embed failed for node %r: %s", label, e)
        try:
            row = db.memory_graph_node_insert(
                dashboard_id=dashboard_id,
                kind=kind,
                label=label,
                summary=summary,
                payload={},
                importance=1.0,
                embedding=emb,
                confidence=conf_f,
                source="extract",
                last_verified=None,
                subject_key=sk,
                stability=stab,
                priority=prio,
            )
            id_by_index[i] = int(row["id"])
        except Exception as ex:
            logger.warning("graph propose: node insert failed: %s", ex)

    applied_edges = 0
    for e in edges_raw:
        if not isinstance(e, dict):
            continue
        try:
            si = int(e.get("src"))
            di = int(e.get("dst"))
        except (TypeError, ValueError):
            continue
        if si < 0 or di < 0 or si >= len(id_by_index) or di >= len(id_by_index):
            continue
        if si == di:
            continue
        a = id_by_index[si]
        b = id_by_index[di]
        if a is None or b is None:
            continue
        rel = str(e.get("rel_type") or "related").strip() or "related"
        try:
            db.memory_graph_edge_insert(
                src_node_id=a,
                dst_node_id=b,
                rel_type=rel,
                weight=1.0,
            )
            applied_edges += 1
        except Exception as ex:
            logger.warning("graph propose: edge insert failed: %s", ex)

    inserted = [x for x in id_by_index if x is not None]
    return {
        "ok": True,
        "proposal": proposal,
        "applied": True,
        "node_ids": inserted,
        "edges_applied": applied_edges,
    }


def _parse_json_loose(content: str) -> Any:
    s = content.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", s)
    if m:
        s = m.group(0)
    return json.loads(s)
