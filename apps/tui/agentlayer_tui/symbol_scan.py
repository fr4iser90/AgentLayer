"""Local symbol + markdown scan for client workspaces (ADR 0009).

The TUI must not import backend modules. Regex fallbacks cover the same suffixes the
server indexes; tree-sitter is used when it is already installed on the laptop.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .jail import JailError, resolve_under_root

_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
    }
)
_SUFFIX_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
}
_MAX_FILE_BYTES = 1_000_000
_MAX_FILES = 5000
_MAX_SYMBOLS = 200
_MAX_MD_FILES = 500
_MAX_MD_BYTES = 2_000_000
_MAX_SIGNATURE = 200

_PY_FN = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.M)
_PY_CLS = re.compile(r"^class\s+([A-Za-z_]\w*)\b", re.M)
_JS_FN = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(|^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(",
    re.M,
)
_JS_CLS = re.compile(r"^(?:export\s+)?class\s+([A-Za-z_]\w*)\b", re.M)
_GO_FN = re.compile(r"^func\s+(?:\([^)]+\)\s+)?([A-Za-z_]\w*)\s*\(", re.M)
_GO_TYPE = re.compile(r"^type\s+([A-Za-z_]\w*)\s+", re.M)
_RS_FN = re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*[\(<]", re.M)
_RS_TYPE = re.compile(r"^(?:pub\s+)?(?:struct|enum|trait|type)\s+([A-Za-z_]\w*)\b", re.M)
_JAVA_CLS = re.compile(
    r"^(?:public|protected|private|abstract|final|\s)*class\s+([A-Za-z_]\w*)\b", re.M
)
_JAVA_FN = re.compile(
    r"^(?:public|protected|private|static|final|synchronized|\s)+[\w.<>,\[\]]+\s+([A-Za-z_]\w*)\s*\(",
    re.M,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _sig(line: str) -> str:
    return line.strip()[:_MAX_SIGNATURE]


def _regex_symbols(text: str, language: str) -> list[dict[str, Any]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    if language == "python":
        patterns = [("function", _PY_FN), ("class", _PY_CLS)]
    elif language in ("javascript", "typescript"):
        patterns = [("function", _JS_FN), ("class", _JS_CLS)]
    elif language == "go":
        patterns = [("function", _GO_FN), ("class", _GO_TYPE)]
    elif language == "rust":
        patterns = [("function", _RS_FN), ("class", _RS_TYPE)]
    elif language == "java":
        patterns = [("class", _JAVA_CLS), ("function", _JAVA_FN)]
    else:
        patterns = [("function", _PY_FN), ("class", _PY_CLS)]
    out: list[dict[str, Any]] = []
    lines = text.splitlines()
    for kind, pat in patterns:
        for m in pat.finditer(text):
            name = next((g for g in m.groups() if g), None)
            if not name:
                continue
            line = _line_of(text, m.start())
            src = lines[line - 1] if 0 < line <= len(lines) else name
            out.append(
                {
                    "kind": kind,
                    "name": name,
                    "line": line,
                    "col": 0,
                    "end_line": line,
                    "end_col": 0,
                    "signature": _sig(src),
                }
            )
            if len(out) >= _MAX_SYMBOLS:
                return out
    return out


def _iter_files(root: Path, suffixes: set[str], *, max_files: int) -> list[Path]:
    root_r = root.resolve()
    found: list[Path] = []
    for fp in sorted(root_r.rglob("*")):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in suffixes:
            continue
        try:
            rel_parts = fp.relative_to(root_r).parts
        except ValueError:
            continue
        if any(part.startswith(".") or part in _SKIP_DIRS for part in rel_parts):
            continue
        try:
            resolve_under_root(root_r, "/".join(rel_parts))
        except JailError:
            continue
        found.append(fp)
        if len(found) >= max_files:
            break
    return found


def scan_symbols(root: Path, *, max_files: int = _MAX_FILES) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(files payload, errors)``. Paths are relative and jail-checked."""
    errors: list[str] = []
    root_r = root.expanduser().resolve()
    files: list[dict[str, Any]] = []
    for fp in _iter_files(root_r, set(_SUFFIX_LANG), max_files=max_files):
        try:
            if fp.stat().st_size > _MAX_FILE_BYTES:
                errors.append(f"{fp.name}: skipped (>{_MAX_FILE_BYTES} bytes)")
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{fp}: {exc}")
            continue
        rel = fp.relative_to(root_r).as_posix()
        language = _SUFFIX_LANG.get(fp.suffix.lower(), "")
        files.append(
            {
                "path": rel,
                "sha256": _sha256(fp),
                "language": language,
                "symbols": _regex_symbols(text, language),
            }
        )
    return files, errors


def scan_markdown(root: Path, *, max_files: int = _MAX_MD_FILES) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    root_r = root.expanduser().resolve()
    docs: list[dict[str, str]] = []
    for fp in _iter_files(root_r, {".md"}, max_files=max_files):
        try:
            if fp.stat().st_size > _MAX_MD_BYTES:
                errors.append(f"{fp.name}: skipped (>{_MAX_MD_BYTES} bytes)")
                continue
            text = fp.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            errors.append(f"{fp}: {exc}")
            continue
        if not text:
            continue
        docs.append({"path": fp.relative_to(root_r).as_posix(), "text": text})
    return docs, errors
