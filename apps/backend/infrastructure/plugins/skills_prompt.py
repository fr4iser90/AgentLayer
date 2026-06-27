"""Skills: ``plugins/skills`` Python plugins (like tool plugins) + optional operator file."""

from __future__ import annotations

import logging
from pathlib import Path

import apps.backend.infrastructure.platform.config as _cfg
from apps.backend.infrastructure.plugins.skill_plugins import collect_plugin_skills_markdown

logger = logging.getLogger(__name__)


def load_skills_prompt_suffix_from_file(*, max_chars: int) -> str:
    path = (_cfg.AGENT_SKILLS_PROMPT_FILE or "").strip()
    if not path or max_chars < 1:
        return ""
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.debug("AGENT_SKILLS_PROMPT_FILE unreadable: %s", e)
        return ""
    if len(raw) > max_chars:
        return raw[:max_chars] + "\n\n… (truncated)\n"
    return raw


def load_combined_skills_prompt(agent_id: str, *, delegate_mode: str | None = None) -> str:
    """Build the full ``## Skills`` block: plugin tree first, then optional ``AGENT_SKILLS_PROMPT_FILE``."""
    max_c = max(512, int(_cfg.AGENT_SKILLS_MAX_TOTAL_CHARS))
    budget = max_c
    sections: list[str] = []

    plugin_md = collect_plugin_skills_markdown(
        agent_id, max_chars=budget, delegate_mode=delegate_mode
    )
    if plugin_md:
        block = "### From repo plugins (`plugins/skills`)\n\n" + plugin_md
        sections.append(block)
        budget = max(0, budget - len(block) - 2)

    if budget > 80:
        file_snip = load_skills_prompt_suffix_from_file(max_chars=budget)
        if file_snip:
            sections.append("### From operator file (`AGENT_SKILLS_PROMPT_FILE`)\n\n" + file_snip)

    if not sections:
        return ""
    return "## Skills\n\n" + "\n\n".join(sections)


def load_skills_prompt_suffix() -> str:
    """Operator file only, up to :data:`AGENT_SKILLS_MAX_TOTAL_CHARS` (for narrow call sites / tests)."""
    return load_skills_prompt_suffix_from_file(
        max_chars=max(512, int(_cfg.AGENT_SKILLS_MAX_TOTAL_CHARS)),
    )
