"""Delegate decision call: idle auto-respond → synthetic user message (no tools)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from apps.backend.domain.delegate_merge import build_delegate_context_block, merge_delegate_configs

logger = logging.getLogger(__name__)


class DelegateDecisionDependencies(Protocol):
    def post_catalog_chat_completions(self, **kwargs: Any) -> tuple[dict[str, Any], Any]: ...


_deps: DelegateDecisionDependencies | None = None


def register_delegate_decision_dependencies(deps: DelegateDecisionDependencies) -> None:
    global _deps
    _deps = deps


def post_catalog_chat_completions(**kwargs: Any) -> tuple[dict[str, Any], Any]:
    if _deps is None:
        raise RuntimeError("delegate decision dependencies not registered")
    return _deps.post_catalog_chat_completions(**kwargs)

_DECISION_SYSTEM = """You are the user's delegate (Stellvertreter): decide the next concrete step on their behalf.
Reply with ONE JSON object only (no markdown fences):
{
  "decision_summary": "one sentence rationale for logs",
  "synthetic_user_message": "short imperative instruction the assistant should execute next",
  "escalate": false,
  "escalate_reason": ""
}
Rules:
- Act on explicit delegate goals and autonomy bounds — do not mimic chat tone.
- Do not ask the user questions; choose a reasonable next action or escalate.
- synthetic_user_message must be actionable (what to do next), not meta commentary.
- If autonomy forbids the implied action, set escalate=true and leave synthetic_user_message empty."""


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None


def _tail_messages(messages: list[dict[str, Any]], *, max_turns: int = 12) -> str:
    lines: list[str] = []
    for m in messages[-max_turns:]:
        role = str(m.get("role") or "user")
        content = m.get("content")
        if isinstance(content, list):
            text = " ".join(
                str(p.get("text") or p.get("content") or "")
                for p in content
                if isinstance(p, dict)
            )
        else:
            text = str(content or "")
        text = text.strip()
        if not text:
            continue
        if len(text) > 2000:
            text = text[:2000] + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines) or "(no prior messages)"


def _autonomy_blocks_action(cfg: dict[str, Any], synthetic: str) -> tuple[bool, str]:
    """Heuristic deny when synthetic message implies forbidden autonomy."""
    aut = cfg.get("autonomy") or {}
    low = synthetic.lower()
    if not aut.get("can_merge_prs") and any(
        k in low for k in ("merge pr", "merge pull", "squash and merge")
    ):
        return True, "autonomy.can_merge_prs is false"
    if not aut.get("can_force_push") and "force push" in low:
        return True, "autonomy.can_force_push is false"
    if not aut.get("can_fix_minor_issues") and any(
        k in low for k in ("deploy to prod", "production deploy", "drop table", "delete database")
    ):
        return True, "autonomy.can_fix_minor_issues is false"
    esc = cfg.get("escalation") or {}
    if esc.get("ask_on_production_changes") and any(
        k in low for k in ("production", "prod deploy", "live deploy")
    ):
        return True, "escalation.ask_on_production_changes is true"
    return False, ""


def run_delegate_decision(
    *,
    messages: list[dict[str, Any]],
    user_config: dict[str, Any] | None,
    workspace_config: dict[str, Any] | None = None,
    workspace_label: str | None = None,
    task_goal: str | None = None,
    task_requirements: str | None = None,
) -> dict[str, Any]:
    """Return decision_summary, synthetic_user_message, escalate, escalate_reason."""
    cfg = merge_delegate_configs(user_config, workspace_config)
    delegate_block = build_delegate_context_block(
        user_config=user_config,
        workspace_config=workspace_config,
        workspace_label=workspace_label,
    )
    task_block = ""
    if task_goal or task_requirements:
        task_block = "## Active task\n"
        if task_goal:
            task_block += f"Goal: {task_goal.strip()[:2000]}\n"
        if task_requirements:
            task_block += f"Requirements: {task_requirements.strip()[:2000]}\n"

    user_payload = (
        f"{delegate_block}\n\n{task_block}\n## Recent conversation\n"
        f"{_tail_messages(messages)}\n\n"
        "Decide the single best next step for the assistant to execute."
    )

    data, _ = post_catalog_chat_completions(
        messages=[
            {"role": "system", "content": _DECISION_SYSTEM},
            {"role": "user", "content": user_payload},
        ],
        timeout=90.0,
        temperature=0.2,
        max_tokens=600,
    )
    choice0 = (data.get("choices") or [{}])[0]
    msg = (choice0.get("message") or {}) if isinstance(choice0, dict) else {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("delegate decision model returned empty content")

    parsed = _parse_json_loose(content)
    if not parsed:
        raise ValueError("delegate decision model did not return JSON")

    summary = str(parsed.get("decision_summary") or "").strip()[:4000]
    synthetic = str(parsed.get("synthetic_user_message") or "").strip()[:8000]
    escalate = bool(parsed.get("escalate"))
    escalate_reason = str(parsed.get("escalate_reason") or "").strip()[:500]

    blocked, block_reason = _autonomy_blocks_action(cfg, synthetic)
    if blocked:
        escalate = True
        escalate_reason = block_reason or escalate_reason
        synthetic = ""

    if escalate and not escalate_reason:
        escalate_reason = "delegate escalated"

    return {
        "decision_summary": summary or ("Escalated" if escalate else "Continue"),
        "synthetic_user_message": synthetic,
        "escalate": escalate,
        "escalate_reason": escalate_reason,
    }
