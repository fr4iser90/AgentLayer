"""Emit in-app notifications from scheduler runs and agent dashboard tools."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.infrastructure import notifications_store
from apps.backend.infrastructure.notifications_delivery import deliver_external

logger = logging.getLogger(__name__)


def emit_notification(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    link_path: str | None = None,
    source_ref: dict[str, Any] | None = None,
) -> None:
    """Insert in-app notification and deliver to opted-in external channels."""
    try:
        from apps.backend.domain.identity import get_benchmark_run_id

        bench_run_id = get_benchmark_run_id()
        if bench_run_id is not None:
            logger.debug(
                "skip notification during benchmark run=%s kind=%s",
                bench_run_id,
                kind,
            )
            return
    except Exception:
        pass

    def _run() -> None:
        row = notifications_store.insert_notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            severity=severity,
            link_path=link_path,
            source_ref=source_ref,
        )
        deliver_external(user_id=user_id, notification=row)

    _safe_emit(_run)


def _safe_emit(fn: Any) -> None:
    try:
        fn()
    except Exception:
        logger.exception("notification emit failed")


def _job_title(row: dict[str, Any]) -> str:
    t = str(row.get("title") or "").strip()
    if t:
        return t
    return str(row.get("id") or "Schedule")


def notify_scheduler_job_finished(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    row: dict[str, Any],
    success: bool,
    error: str | None = None,
    run_id: str | None = None,
) -> None:
    job_id = str(row.get("id") or "")
    title = _job_title(row)
    link = "/app/schedules"
    if run_id:
        link = f"/app/schedules?run={run_id}"
    ref: dict[str, Any] = {"job_id": job_id}
    dash = row.get("dashboard_id")
    if dash is not None:
        ref["dashboard_id"] = str(dash)

    if success:
        emit_notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind="scheduler_job_done",
            severity="info",
            title=f"Schedule finished: {title}",
            body="Background job completed successfully.",
            link_path=link,
            source_ref=ref,
        )
    else:
        err = (error or "Job failed").strip()[:500]
        emit_notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind="scheduler_job_failed",
            severity="warning",
            title=f"Schedule failed: {title}",
            body=err,
            link_path=link,
            source_ref=ref,
        )


def infer_block_ids_from_patches(
    patches: list[Any],
    ui_layout: dict[str, Any] | None,
) -> list[str]:
    """Map data patch paths to block ids via ``props.dataPath`` (root + nested sections)."""
    if not isinstance(ui_layout, dict):
        return []
    top_keys: set[str] = set()
    for p in patches:
        if not isinstance(p, dict):
            continue
        path = str(p.get("path") or "").strip()
        if not path or path.startswith("_"):
            continue
        top = path.split(".", 1)[0]
        if top:
            top_keys.add(top)
    if not top_keys:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def walk_blocks(blocks: Any) -> None:
        if not isinstance(blocks, list):
            return
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bid = str(b.get("id") or "").strip()
            props = b.get("props")
            dp = str(props.get("dataPath") or "").strip() if isinstance(props, dict) else ""
            if bid and dp:
                root = dp.split(".", 1)[0]
                if root in top_keys or dp in top_keys:
                    if bid not in seen:
                        seen.add(bid)
                        out.append(bid)
            if str(b.get("type") or "") == "section" and isinstance(props, dict):
                nested = props.get("nested")
                if isinstance(nested, dict):
                    walk_blocks(nested.get("blocks"))

    walk_blocks(ui_layout.get("blocks"))
    return out


def notify_dashboard_agent_update(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    dashboard_id: uuid.UUID,
    dashboard_title: str,
    patches: list[Any],
    ui_layout: dict[str, Any] | None,
) -> None:
    did = str(dashboard_id)
    block_ids = infer_block_ids_from_patches(patches, ui_layout)
    n = len(patches) if isinstance(patches, list) else 0
    title = (dashboard_title or "").strip() or "Dashboard"
    body = f"Agent updated {n} data field(s)."
    link = f"/app/dashboard?id={did}"

    def _insert(block_id: str | None) -> None:
        ref: dict[str, Any] = {"dashboard_id": did}
        link = f"/app/dashboard?id={did}"
        if block_id:
            ref["block_id"] = block_id
            link = f"{link}&block={block_id}"
        emit_notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind="dashboard_agent_update",
            severity="info",
            title=f"Dashboard updated: {title}",
            body=body,
            link_path=link,
            source_ref=ref,
        )

    if block_ids:
        for bid in block_ids[:12]:
            _safe_emit(lambda b=bid: _insert(b))
    else:
        _safe_emit(lambda: _insert(None))
