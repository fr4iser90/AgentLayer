"""Persist SimpleSecCheck scan summaries as agent artifacts for delegate handoff."""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_CONTEXT_KEY = "_ssc_scan_artifact_ids"


def _user_and_tenant(context: dict[str, Any] | None) -> tuple[uuid.UUID | None, int | None]:
    ctx = context or {}
    uid: uuid.UUID | None = None
    u = ctx.get("user")
    if u is not None:
        raw = getattr(u, "id", None)
        if raw is not None:
            try:
                uid = uuid.UUID(str(raw))
            except (ValueError, TypeError):
                uid = None
    tid: int | None = None
    if uid is not None:
        try:
            from apps.backend.infrastructure.db import db as _db

            tid = _db.user_tenant_id(uid)
        except Exception:
            tid = None
    if tid is None:
        try:
            from apps.backend.domain.identity import get_identity

            t, u2 = get_identity()
            if t is not None:
                tid = int(t)
            if uid is None and u2 is not None:
                uid = u2
        except Exception:
            pass
    return uid, tid


def _workspace_uuid(context: dict[str, Any] | None) -> uuid.UUID | None:
    ctx = context or {}
    ws = ctx.get("workspace")
    if isinstance(ws, dict) and ws.get("id"):
        try:
            return uuid.UUID(str(ws["id"]))
        except (ValueError, TypeError):
            return None
    wid = ctx.get("workspace_id")
    if wid:
        try:
            return uuid.UUID(str(wid))
        except (ValueError, TypeError):
            return None
    return None


def _compact_finding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: row[k]
        for k in ("tool", "rule_id", "severity", "path", "line", "message", "cwe", "fix_hint")
        if row.get(k) not in (None, "")
    }


def maybe_persist_ssc_scan_artifact(
    context: dict[str, Any] | None,
    *,
    scan_id: str | None,
    summary: Any = None,
    findings: list[dict[str, Any]] | None = None,
    repo_url: str | None = None,
    branch: str | None = None,
    severity_filter: str | None = None,
) -> str | None:
    """Create one artifact per scan_id per agent run; return artifact UUID string."""
    sid = (scan_id or "").strip()
    if not sid:
        return None
    rows = [_compact_finding(dict(f)) for f in (findings or []) if isinstance(f, dict)]
    if not rows and summary is None:
        return None

    ctx = context if isinstance(context, dict) else {}
    cache = ctx.setdefault(_CONTEXT_KEY, {})
    if isinstance(cache, dict) and sid in cache:
        return str(cache[sid])

    uid, tid = _user_and_tenant(ctx)
    if uid is None or tid is None:
        return None

    high_paths: list[str] = []
    for f in rows:
        sev = str(f.get("severity") or "").upper()
        path = str(f.get("path") or "").strip()
        if path and sev in ("CRITICAL", "HIGH"):
            if path not in high_paths:
                high_paths.append(path)

    sev_counts: dict[str, int] = {}
    for f in rows:
        sev = str(f.get("severity") or "UNKNOWN").upper()
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    summary_line = f"SSC scan {sid}"
    if sev_counts:
        parts = [f"{k}:{v}" for k, v in sorted(sev_counts.items())]
        summary_line += " (" + ", ".join(parts) + ")"

    from apps.backend.infrastructure import agent_artifacts_store

    try:
        art = agent_artifacts_store.create_artifact(
            tenant_id=int(tid),
            created_by_user_id=uid,
            kind="ssc_scan",
            summary=summary_line[:2000],
            content={
                "scan_id": sid,
                "repo_url": repo_url,
                "branch": branch,
                "severity_filter": severity_filter,
                "summary": summary,
                "finding_count": len(rows),
                "findings": rows[:200],
                "high_paths": high_paths[:80],
                "handoff_hint": (
                    "Pass this artifact_id to agent_delegate artifact_refs when delegating "
                    "fixes to coding. Fix listed paths only — do not grep subprocess/execute/SELECT."
                ),
            },
            workspace_id=_workspace_uuid(ctx),
            metadata={"scan_id": sid},
        )
        artifact_id = str(art.get("id") or "")
        if artifact_id and isinstance(cache, dict):
            cache[sid] = artifact_id
        return artifact_id or None
    except Exception:
        logger.warning("ssc_scan artifact persist failed scan_id=%s", sid, exc_info=True)
        return None
