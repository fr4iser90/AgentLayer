from __future__ import annotations

import re
from pathlib import Path


def _path_under_or_equal(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _iter_tool_py_files(root: Path) -> list[Path]:
    """All ``*.py`` under ``root``, excluding package/private/cache files."""
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        out.append(path)
    return out


def _stable_module_slug(directory: Path, path: Path, dir_idx: int) -> str:
    """Unique import-safe suffix for ``spec_from_file_location``."""
    try:
        rel = path.resolve().relative_to(directory.resolve())
    except (ValueError, OSError):
        rel = Path(path.name)
    rel_no_suffix = rel.with_suffix("")
    parts = [re.sub(r"[^a-zA-Z0-9_]", "_", str(p)) for p in rel_no_suffix.parts]
    slug = "_".join(p for p in parts if p).strip("_") or "tool"
    if slug and slug[0].isdigit():
        slug = f"m_{slug}"
    return f"{dir_idx}_{slug}"


__all__ = ["_iter_tool_py_files", "_path_under_or_equal", "_stable_module_slug"]
