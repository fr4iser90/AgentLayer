"""Load skill plugins from ``plugins/skills`` (same plug-in idea as tools under ``plugins/tools``)."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apps.backend.core.config import skill_scan_directories

logger = logging.getLogger(__name__)

_SKILL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)


def _iter_skill_files(root: Path) -> list[Path]:
    """``*.py`` and ``*.md`` under ``root`` (recursive), excluding cache and README."""
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix == ".py":
            if path.name.startswith("_") or path.name == "__init__.py":
                continue
            out.append(path)
        elif path.suffix == ".md":
            if path.name.startswith("_") or path.name.lower() == "readme.md":
                continue
            out.append(path)
    return out


def _coerce_agent_filter(raw: Any) -> frozenset[str] | None:
    """
    Restrict skill to these agent ids.

    Missing, empty string, or empty collection → ``None`` (apply to any skill-enabled agent).
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return frozenset(items) if items else None
    if isinstance(raw, (list, tuple, set, frozenset)):
        items = [str(x).strip() for x in raw if str(x).strip()]
        return frozenset(items) if items else None
    return None


def _coerce_agent_filter_mod(mod: Any) -> frozenset[str] | None:
    if not hasattr(mod, "SKILL_AGENTS"):
        return None
    return _coerce_agent_filter(getattr(mod, "SKILL_AGENTS"))


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
    exclude_agents: frozenset[str] | None = None
    when_delegate_mode: str | None = None


def _coerce_optional_str(raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return None


def _skill_matches_agent(
    parsed: _ParsedSkill,
    agent_id: str,
    *,
    delegate_mode: str | None = None,
) -> bool:
    if parsed.agents is not None and agent_id not in parsed.agents:
        return False
    if parsed.exclude_agents is not None and agent_id in parsed.exclude_agents:
        return False
    if parsed.when_delegate_mode:
        mode = (delegate_mode or "").strip().lower()
        if mode != parsed.when_delegate_mode:
            return False
    return True


def _meta_parsed_skill(
    *,
    skill_id: str,
    text: str,
    meta: dict[str, Any],
) -> _ParsedSkill:
    return _ParsedSkill(
        skill_id=skill_id,
        text=text,
        agents=_coerce_agent_filter(meta.get("agents") or meta.get("SKILL_AGENTS")),
        exclude_agents=_coerce_agent_filter(meta.get("exclude_agents")),
        when_delegate_mode=_coerce_optional_str(
            meta.get("when_delegate_mode") or meta.get("delegate_mode")
        ),
    )


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
    agents = _coerce_agent_filter_mod(mod)
    return _ParsedSkill(skill_id=skill_id, text=text, agents=agents)


def _parse_skill_md(skill_md: Path) -> _ParsedSkill | None:
    try:
        raw = skill_md.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("cannot read skill %s: %s", skill_md, e)
        return None

    meta: dict[str, Any] = {}
    text = raw.strip()
    match = _FRONTMATTER_RE.match(raw)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1))
        except yaml.YAMLError as e:
            logger.warning("skill %s: invalid YAML frontmatter: %s", skill_md, e)
            return None
        meta = loaded if isinstance(loaded, dict) else {}
        text = raw[match.end() :].strip()

    sid = meta.get("skill_id") or meta.get("SKILL_ID")
    if not isinstance(sid, str) or not sid.strip():
        logger.warning("skill %s: missing or invalid skill_id in frontmatter", skill_md)
        return None
    skill_id = sid.strip()
    if not _SKILL_ID_RE.match(skill_id):
        logger.warning("skill %s: skill_id %r must match %s", skill_md, skill_id, _SKILL_ID_RE.pattern)
        return None
    if not text:
        logger.debug("skill %s (%s): empty body, skipping", skill_md, skill_id)
        return None
    return _meta_parsed_skill(skill_id=skill_id, text=text, meta=meta)


def _parse_skill_file(path: Path) -> _ParsedSkill | None:
    if path.suffix == ".md":
        return _parse_skill_md(path)
    if path.suffix == ".py":
        return _parse_skill_py(path)
    return None


def _iter_parsed_skills() -> list[_ParsedSkill]:
    seen: set[str] = set()
    out: list[_ParsedSkill] = []
    for root in skill_scan_directories():
        for path in _iter_skill_files(root):
            parsed = _parse_skill_file(path)
            if not parsed or parsed.skill_id in seen:
                if parsed and parsed.skill_id in seen:
                    logger.warning(
                        "duplicate SKILL_ID %r in %s — skipping (first wins)", parsed.skill_id, path
                    )
                continue
            seen.add(parsed.skill_id)
            out.append(parsed)
    return out


def load_skill_text_by_id(skill_id: str) -> str | None:
    """Return skill body for ``skill_id`` (no agent/delegate filtering)."""
    want = (skill_id or "").strip()
    if not want:
        return None
    for parsed in _iter_parsed_skills():
        if parsed.skill_id == want:
            return parsed.text
    return None


def collect_plugin_skills_markdown(
    agent_id: str,
    *,
    max_chars: int,
    delegate_mode: str | None = None,
) -> str:
    """
    Concatenate skill bodies for ``agent_id``.

    Frontmatter ``agents`` / ``exclude_agents`` / ``when_delegate_mode`` filter inclusion.
    """
    seen: set[str] = set()
    chunks: list[str] = []
    used = 0
    aid = (agent_id or "").strip()
    if not aid:
        return ""
    for parsed in _iter_parsed_skills():
        if not _skill_matches_agent(parsed, aid, delegate_mode=delegate_mode):
            continue
        if parsed.skill_id in seen:
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
