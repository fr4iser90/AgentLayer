"""Directory scan helpers for plugin-backed tools and skills."""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def tool_scan_directories(*, plugins_dir: Path, tools_extra_dir: str) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            logger.warning("tool directory not resolvable: %s", p)
            return
        if r.is_dir() and str(r) not in seen:
            seen.add(str(r))
            out.append(r)

    raw = (os.environ.get("AGENT_TOOL_DIRS") or "").strip()
    if raw:
        for part in raw.split(","):
            add(Path(part.strip()).expanduser())
        return out

    add(plugins_dir / "tools")
    add(plugins_dir / "workflows")
    if tools_extra_dir:
        add(Path(tools_extra_dir).expanduser())
    return out


def skill_scan_directories(*, plugins_dir: Path) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            logger.warning("skill directory not resolvable: %s", p)
            return
        if r.is_dir() and str(r) not in seen:
            seen.add(str(r))
            out.append(r)

    raw = (os.environ.get("AGENT_SKILL_DIRS") or "").strip()
    if raw:
        for part in raw.split(","):
            add(Path(part.strip()).expanduser())
        return out

    add(plugins_dir / "skills")
    return out
