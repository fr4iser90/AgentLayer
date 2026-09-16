"""Use cases for the agent submission staging + review queue (P7a).

Thin orchestration over ``agent_submission_store`` (DB) and
``agent_submission_materialize`` (filesystem promotion). On approve, the draft
is materialized into ``plugins/agents`` and the live agent registry reloaded;
a filesystem/reload failure is captured on the row, never aborting the review.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from apps.backend.infrastructure.agent_runtime import (
    agent_submission_materialize as materialize,
)
from apps.backend.infrastructure.agent_runtime import agent_submission_store as store

logger = logging.getLogger(__name__)


def _reload_agent_registry() -> None:
    try:
        from apps.backend.domain.agent_runtime.registry import get_agent_registry

        get_agent_registry().reload()
    except Exception as exc:  # noqa: BLE001 - surfaced as materialize_error, never fatal
        logger.warning("agent registry reload failed: %s", exc)


def submit_agent_submission(
    *,
    author_id: str,
    agent_id: str,
    agent_yaml: dict[str, Any],
    title: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    target_dir: str | None = None,
) -> dict[str, Any]:
    return store.create_submission(
        agent_id=agent_id,
        agent_yaml=agent_yaml,
        title=title,
        description=description,
        system_prompt=system_prompt,
        target_dir=target_dir,
        author_id=author_id,
    )


def _tool_warnings(agent_yaml: dict[str, Any]) -> list[str]:
    try:
        from apps.backend.domain.plugin_system.registry import get_registry

        known = set()
        for entry in get_registry().tools_meta or []:
            for name in entry.get("tools") or []:
                known.add(str(name))
    except Exception:  # noqa: BLE001 - warnings are advisory only
        return []
    warned: list[str] = []
    for tool in agent_yaml.get("tool_allowlist") or []:
        if str(tool) not in known:
            warned.append(str(tool))
    return warned


def assess_submission(
    *,
    author_id: str,
    agent_id: str,
    agent_yaml: dict[str, Any],
    system_prompt: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Heuristic pre-filter for a proposed draft: risk, unknown tools and notes.

    No row is written — the controller exposes this as
    ``POST /agents/submissions/assess`` so submitters can sanity-check a draft
    before it enters the review queue.
    """
    assessed = store.assess_submission(
        agent_id=agent_id, agent_yaml=agent_yaml, system_prompt=system_prompt
    )
    payload = assessed["agent_yaml"]
    warnings = _tool_warnings(payload)
    notes: list[str] = []
    if assessed["risk_level"] == "high":
        notes.append("High-risk agent: it mentions privileged, exec, shell or credential actions.")
    if warnings:
        notes.append("Unknown tools: " + ", ".join(warnings))
    if not str(payload.get("description") or "").strip():
        notes.append("No description provided.")
    return {
        "agent_id": assessed["slug"],
        "author_id": author_id,
        "title": title or str(payload.get("name") or ""),
        "description": description or str(payload.get("description") or ""),
        "system_prompt": system_prompt if system_prompt else str(payload.get("system_prompt") or ""),
        "risk_level": assessed["risk_level"],
        "tool_warnings": warnings,
        "target_dir": assessed["target_dir"],
        "notes": notes,
    }


def preview_submission(submission_id: str) -> dict[str, Any] | None:
    row = store.get_submission(submission_id)
    if not row:
        return None
    payload = row.get("agent_yaml") or {}
    row = dict(row)
    row["tool_warnings"] = _tool_warnings(payload)
    row["yaml_text"] = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return row


def list_submissions(
    *,
    status: str | None = None,
    author_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return store.list_submissions(status=status, author_id=author_id, agent_id=agent_id, limit=limit)


def review_submission(
    *,
    submission_id: str,
    decision: str,
    reviewed_by: str,
    review_notes: str | None = None,
) -> dict[str, Any]:
    updated = store.review_submission(
        submission_id=submission_id,
        decision=decision,
        reviewed_by=reviewed_by,
        review_notes=review_notes,
    )
    result: dict[str, Any] = {"submission": updated, "materialize": None}
    if str(decision).strip().lower() == "approve":
        mat = materialize.materialize_submission(
            submission=updated, reload_agent_registry=_reload_agent_registry
        )
        result["materialize"] = mat
        if not mat.get("ok"):
            store.set_materialize_error(submission_id, mat.get("error"))
            refreshed = store.get_submission(submission_id)
            if refreshed:
                result["submission"] = refreshed
    return result
