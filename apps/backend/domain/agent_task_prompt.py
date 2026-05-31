"""Build sub-agent prompts from artifact references (avoid huge chat context)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure import agent_artifacts_store


def _parse_uuid_list(raw: Any) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    if raw is None:
        return out
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return out
    for item in raw:
        try:
            out.append(uuid.UUID(str(item).strip()))
        except (ValueError, TypeError):
            continue
    return out


def format_requirements_block(requirements: Any) -> str:
    if not requirements:
        return ""
    if isinstance(requirements, str):
        return requirements.strip()
    if isinstance(requirements, list):
        lines = [str(x).strip() for x in requirements if str(x).strip()]
        if not lines:
            return ""
        mode_hints = _delegate_mode_hints_from_requirements(lines)
        body = "Requirements:\n" + "\n".join(f"- {ln}" for ln in lines)
        if mode_hints:
            body = mode_hints + "\n\n" + body
        return body
    return ""


def parse_delegate_mode(requirements: Any) -> str | None:
    if requirements is None:
        return None
    if isinstance(requirements, str):
        requirements = [requirements]
    if not isinstance(requirements, list):
        return None
    for ln in requirements:
        low = str(ln).lower().strip()
        if low.startswith("mode:"):
            mode = low.split(":", 1)[1].strip()
            return mode or None
    return None


_GIT_FORENSICS_PROMPT_SIGNALS = (
    "git branch",
    "git log",
    "git status",
    "diff_stat",
    "commits on",
    "check branch",
    "verify branch",
    "branch and commit",
    "branch status",
)


def infer_plan_delegate_mode(prompt: str, requirements: Any = None) -> str | None:
    mode = parse_delegate_mode(requirements)
    if mode:
        return mode
    low = (prompt or "").lower()
    if any(sig in low for sig in _GIT_FORENSICS_PROMPT_SIGNALS):
        return "git_forensics"
    return None


_DELEGATE_MODE_HINTS: dict[str, str] = {
    "git_forensics": (
        "## Delegate mode: git_forensics\n"
        "Workflow (strict order):\n"
        "1. ``git_read``: branch, status, log, **diff_stat**\n"
        "2. ``read_file`` on paths from diff_stat or the task\n"
        "3. ``search`` **only** with ``path_prefix`` set to a **changed file's directory** "
        "(e.g. ``plugins/tools/capabilities/coding/`` — never ``apps``, ``plugins``, or ``scripts`` alone)\n"
        "Do **not** use ``retrieve_context``, ``semantic_search``, or repo-wide grep before step 1–2."
    ),
    "fix_from_artifact": (
        "## Delegate mode: fix_from_artifact\n"
        "Fix **only** paths from ``[Referenced artifacts]`` (``paths``, ``high_paths``, or ``findings[].path``).\n"
        "Workflow: checkout the ``branch: …`` requirement when present → ``read_file`` each path → "
        "patch → commit → push **that** branch. Verify with ``git_read`` log and re-read edited files "
        "before finishing."
    ),
}


def _delegate_mode_hints_from_requirements(lines: list[str]) -> str:
    hints: list[str] = []
    for ln in lines:
        low = ln.lower().strip()
        if low.startswith("mode:"):
            mode = low.split(":", 1)[1].strip()
            block = _DELEGATE_MODE_HINTS.get(mode)
            if block and block not in hints:
                hints.append(block)
    return "\n\n".join(hints)


def build_artifact_context_block(
    *,
    tenant_id: int,
    artifact_refs: Any,
    max_artifacts: int = 8,
    max_chars_per_artifact: int = 6000,
) -> str:
    ids = _parse_uuid_list(artifact_refs)[:max_artifacts]
    if not ids:
        return ""
    blocks: list[str] = []
    for aid in ids:
        row = agent_artifacts_store.get_artifact(artifact_id=aid, tenant_id=tenant_id)
        if not row:
            blocks.append(f"[Artifact {aid} — not found]")
            continue
        kind = row.get("kind") or "artifact"
        summary = (row.get("summary") or "").strip()
        content = row.get("content") or {}
        text = ""
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                text = content["text"]
            elif isinstance(content.get("assistant_excerpt"), str):
                text = content["assistant_excerpt"]
            else:
                text = json.dumps(content, ensure_ascii=False, default=str)
        elif content is not None:
            text = str(content)
        text = text.strip()
        if len(text) > max_chars_per_artifact:
            text = text[:max_chars_per_artifact] + "\n…(truncated)"
        blocks.append(
            f"### Artifact `{aid}` ({kind})\n"
            f"{summary}\n\n{text}".strip()
        )
    if not blocks:
        return ""
    return "[Referenced artifacts]\n\n" + "\n\n---\n\n".join(blocks)


def build_agent_tasks_context_snippet(*, active_task_id: str | None = None) -> str:
    lines = [
        "## Agent tasks & artifacts",
        "Long-running work lives in **agent_tasks**, not chat history. Use:",
        "- `task_create` / `task_list` / `task_update` for global or workspace backlog",
        "- `artifact_get` to load prior outputs by id",
        "- `delegate` with `artifact_refs`, `requirements`, optional `task_id` for specialists",
        "Summarize artifacts for the user; do not dump raw sub-agent transcripts.",
    ]
    if active_task_id:
        lines.append(f"Active task for this conversation: `{active_task_id}`.")
    return "\n".join(lines)


def enrich_delegate_prompt(
    *,
    tenant_id: int,
    base_prompt: str,
    artifact_refs: Any = None,
    requirements: Any = None,
) -> str:
    parts: list[str] = []
    req = format_requirements_block(requirements)
    if req:
        parts.append(req)
    art = build_artifact_context_block(tenant_id=tenant_id, artifact_refs=artifact_refs)
    if art:
        parts.append(art)
    base = (base_prompt or "").strip()
    if base:
        if parts:
            parts.append("---\nTask instructions:\n" + base)
        else:
            parts.append(base)
    return "\n\n".join(parts).strip()
