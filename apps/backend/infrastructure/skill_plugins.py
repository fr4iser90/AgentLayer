"""Load skill plugins from ``plugins/skills`` (same plug-in idea as tools under ``plugins/tools``)."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.backend.core.config import skill_scan_directories

logger = logging.getLogger(__name__)

_SKILL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _iter_skill_py_files(root: Path) -> list[Path]:
    """``*.py`` under ``root`` (recursive), excluding ``__init__.py``, ``_*``, ``__pycache__``."""
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        out.append(path)
    return out


def _coerce_agent_filter(mod: Any) -> frozenset[str] | None:
    """
    ``SKILL_AGENTS``: restrict to these agent ids.

    Missing attribute, empty string, or empty collection → ``None`` (apply to any skill-enabled agent).
    """
    if not hasattr(mod, "SKILL_AGENTS"):
        return None
    raw = getattr(mod, "SKILL_AGENTS")
    if isinstance(raw, str):
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return frozenset(items) if items else None
    if isinstance(raw, (list, tuple, set, frozenset)):
        items = [str(x).strip() for x in raw if str(x).strip()]
        return frozenset(items) if items else None
    return None


def _resolve_body_file(skill_py: Path, rel: str) -> str | None:
    rel = (rel or "").strip()
    if not rel or rel.startswith(("/", "\\")):
        return None
    parts = Path(rel).parts
    if ".." in parts:
        return None
    candidate = (skill_py.parent / rel).resolve()
    try:
        candidate.relative_to(skill_py.parent.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("skill %s: cannot read SKILL_BODY_FILE %s: %s", skill_py, rel, e)
        return None


@dataclass(frozen=True)
class _ParsedSkill:
    skill_id: str
    text: str
    agents: frozenset[str] | None


def _parse_skill_py(skill_py: Path) -> _ParsedSkill | None:
    slug = hashlib.sha256(str(skill_py.resolve()).encode()).hexdigest()[:20]
    mod_name = f"agent_skill_{slug}"
    spec = importlib.util.spec_from_file_location(mod_name, skill_py)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        logger.exception("failed to load skill plugin %s", skill_py)
        return None
    sid = getattr(mod, "SKILL_ID", None)
    if not isinstance(sid, str) or not sid.strip():
        logger.warning("skill %s: missing or invalid SKILL_ID", skill_py)
        return None
    skill_id = sid.strip()
    if not _SKILL_ID_RE.match(skill_id):
        logger.warning("skill %s: SKILL_ID %r must match %s", skill_py, skill_id, _SKILL_ID_RE.pattern)
        return None
    body = getattr(mod, "SKILL_BODY", None)
    text = body.strip() if isinstance(body, str) else ""
    body_file = getattr(mod, "SKILL_BODY_FILE", None)
    if isinstance(body_file, str) and body_file.strip() and not text:
        text = _resolve_body_file(skill_py, body_file.strip()) or ""
    if not text:
        logger.debug("skill %s (%s): empty body, skipping", skill_py, skill_id)
        return None
    agents = _coerce_agent_filter(mod)
    return _ParsedSkill(skill_id=skill_id, text=text, agents=agents)


def collect_plugin_skills_markdown(agent_id: str, *, max_chars: int) -> str:
    """
    Concatenate skill bodies for ``agent_id``.

    ``SKILL_AGENTS``: if set and non-empty, only those agent ids receive the skill.
    """
    seen: set[str] = set()
    chunks: list[str] = []
    used = 0
    for root in skill_scan_directories():
        for path in _iter_skill_py_files(root):
            parsed = _parse_skill_py(path)
            if not parsed:
                continue
            if parsed.agents is not None and agent_id not in parsed.agents:
                continue
            if parsed.skill_id in seen:
                logger.warning("duplicate SKILL_ID %r in %s — skipping (first wins)", parsed.skill_id, path)
                continue
            seen.add(parsed.skill_id)
            block = f"### Skill: `{parsed.skill_id}`\n\n{parsed.text}\n"
            if used + len(block) > max_chars:
                logger.warning(
                    "skill plugin output exceeded AGENT_SKILLS_MAX_TOTAL_CHARS=%d; truncating after %s",
                    max_chars,
                    parsed.skill_id,
                )
                remain = max(0, max_chars - used)
                if remain > 80:
                    chunks.append(block[:remain] + "\n\n… (truncated)\n")
                break
            chunks.append(block)
            used += len(block)
    return "\n".join(chunks).strip()
