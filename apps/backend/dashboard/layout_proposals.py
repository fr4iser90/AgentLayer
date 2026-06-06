"""In-memory store for dashboard layout proposals (agent preview → user apply)."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.layout_data_init import (
    merge_data_for_layout,
    new_proposal_id,
    new_proposal_set_id,
)
from apps.backend.dashboard.projects_kpi import projects_data_path, sync_projects_kpis_in_data
from apps.backend.dashboard.template_ops import validate_template_import

_TTL_SEC = 3600
_MAX_PROPOSALS = 3
_lock = threading.Lock()
_store: dict[str, dict[str, Any]] = {}


@dataclass
class LayoutProposal:
    id: str
    title: str
    summary: str
    ui_layout: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "ui_layout": copy.deepcopy(self.ui_layout),
        }


@dataclass
class LayoutProposalSet:
    set_id: str
    tenant_id: int
    user_id: uuid.UUID
    dashboard_id: uuid.UUID
    kind: str
    proposals: list[LayoutProposal] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self, *, include_layouts: bool = True) -> dict[str, Any]:
        props = []
        for p in self.proposals:
            row = {"id": p.id, "title": p.title, "summary": p.summary}
            if include_layouts:
                row["ui_layout"] = copy.deepcopy(p.ui_layout)
            props.append(row)
        return {
            "set_id": self.set_id,
            "dashboard_id": str(self.dashboard_id),
            "kind": self.kind,
            "proposals": props,
            "created_at": self.created_at,
        }


def _purge_expired(now: float | None = None) -> None:
    t = now if now is not None else time.time()
    dead = [k for k, v in _store.items() if t - float(v.get("created_at") or 0) > _TTL_SEC]
    for k in dead:
        _store.pop(k, None)


def store_proposal_set(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    kind: str,
    proposals: list[dict[str, Any]],
) -> tuple[LayoutProposalSet | None, str | None]:
    if not proposals:
        return None, "proposals must be a non-empty array"
    if len(proposals) > _MAX_PROPOSALS:
        return None, f"at most {_MAX_PROPOSALS} proposals per set"
    parsed: list[LayoutProposal] = []
    for i, raw in enumerate(proposals):
        if not isinstance(raw, dict):
            return None, f"proposal[{i}] must be an object"
        title = str(raw.get("title") or f"Option {i + 1}").strip()[:120]
        summary = str(raw.get("summary") or "").strip()[:500]
        ul = raw.get("ui_layout")
        if not isinstance(ul, dict):
            return None, f"proposal[{i}].ui_layout must be an object"
        ul_clean, _, err = validate_template_import(kind=kind, ui_layout=ul, data=None)
        if err:
            return None, f"proposal[{i}]: {err}"
        pid = str(raw.get("id") or "").strip() or new_proposal_id()
        parsed.append(LayoutProposal(id=pid, title=title, summary=summary, ui_layout=ul_clean))
    set_id = new_proposal_set_id()
    row = LayoutProposalSet(
        set_id=set_id,
        tenant_id=tenant_id,
        user_id=user_id,
        dashboard_id=dashboard_id,
        kind=kind,
        proposals=parsed,
    )
    with _lock:
        _purge_expired()
        _store[set_id] = {
            "tenant_id": tenant_id,
            "user_id": str(user_id),
            "dashboard_id": str(dashboard_id),
            "kind": kind,
            "proposals": [p.to_dict() for p in parsed],
            "created_at": row.created_at,
        }
    return row, None


def get_proposal_set(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    set_id: str,
) -> LayoutProposalSet | None:
    with _lock:
        _purge_expired()
        raw = _store.get(set_id)
    if not raw:
        return None
    if int(raw.get("tenant_id") or 0) != tenant_id:
        return None
    if str(raw.get("user_id") or "") != str(user_id):
        return None
    if str(raw.get("dashboard_id") or "") != str(dashboard_id):
        return None
    props = []
    for p in raw.get("proposals") or []:
        if not isinstance(p, dict):
            continue
        ul = p.get("ui_layout")
        if not isinstance(ul, dict):
            continue
        props.append(
            LayoutProposal(
                id=str(p.get("id") or ""),
                title=str(p.get("title") or ""),
                summary=str(p.get("summary") or ""),
                ui_layout=ul,
            )
        )
    if not props:
        return None
    return LayoutProposalSet(
        set_id=set_id,
        tenant_id=tenant_id,
        user_id=user_id,
        dashboard_id=dashboard_id,
        kind=str(raw.get("kind") or "custom"),
        proposals=props,
        created_at=float(raw.get("created_at") or time.time()),
    )


def get_latest_proposal_set(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
) -> LayoutProposalSet | None:
    did = str(dashboard_id)
    uid = str(user_id)
    latest_id: str | None = None
    latest_ts = 0.0
    with _lock:
        _purge_expired()
        for sid, raw in _store.items():
            if int(raw.get("tenant_id") or 0) != tenant_id:
                continue
            if str(raw.get("user_id") or "") != uid:
                continue
            if str(raw.get("dashboard_id") or "") != did:
                continue
            ts = float(raw.get("created_at") or 0)
            if ts >= latest_ts:
                latest_ts = ts
                latest_id = sid
    if not latest_id:
        return None
    return get_proposal_set(
        tenant_id=tenant_id,
        user_id=user_id,
        dashboard_id=dashboard_id,
        set_id=latest_id,
    )


def apply_layout_proposal(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    set_id: str,
    proposal_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    pset = get_proposal_set(
        tenant_id=tenant_id,
        user_id=user_id,
        dashboard_id=dashboard_id,
        set_id=set_id,
    )
    if pset is None:
        return None, "proposal set not found or expired"
    proposal = next((p for p in pset.proposals if p.id == proposal_id), None)
    if proposal is None:
        return None, "proposal not found in set"
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if ws is None:
        return None, "dashboard not found or no access"
    role = (ws.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return None, "read-only access — cannot apply layout"
    if ws.get("access_scope") == "granular":
        return None, "granular block share cannot change layout"
    old_ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    data = dict(ws.get("data") or {})
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        meta = {}
    meta = dict(meta)
    meta["layout_snapshot_before_proposal"] = {
        "set_id": set_id,
        "proposal_id": proposal_id,
        "ui_layout": copy.deepcopy(old_ul),
    }
    data["_agentlayer"] = meta
    new_data = merge_data_for_layout(data, proposal.ui_layout)
    kind = (ws.get("kind") or "").strip().lower()
    if kind == "projects":
        new_data = sync_projects_kpis_in_data(new_data, projects_data_path(ws))
    updated = dashboard_db.dashboard_update(
        user_id,
        tenant_id,
        dashboard_id,
        ui_layout=copy.deepcopy(proposal.ui_layout),
        data=new_data,
    )
    if updated is None:
        return None, "could not update dashboard"
    with _lock:
        _store.pop(set_id, None)
    return updated, None
