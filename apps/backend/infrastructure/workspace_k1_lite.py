"""K1-lite project knowledge extraction for coding workspaces.

Project RAG settings remain independent. The default extractor is deterministic;
optional LLM/hybrid extraction uses a dedicated extractor provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"})
_DOC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})
_CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"})
_MAX_BYTES = 256_000


def _is_candidate(path: Path) -> bool:
    if any(part in _SKIP_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in (_DOC_SUFFIXES | _CODE_SUFFIXES)


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return ""
    return data[:_MAX_BYTES].decode("utf-8", errors="replace")


def _classify_doc_line(line: str) -> str:
    low = line.lower()
    if low.startswith("#"):
        return "entity"
    if any(token in low for token in ("must ", "should ", "requires ", "requirement", "invariant")):
        return "claim"
    return "evidence"


def extract_knowledge_units_for_file(root: Path, path: Path) -> list[dict[str, Any]]:
    rel = path.relative_to(root).as_posix()
    text = _read_text(path)
    if not text.strip():
        return []
    suffix = path.suffix.lower()
    units: list[dict[str, Any]] = []
    section = ""
    lines = text.splitlines()

    if suffix in _DOC_SUFFIXES:
        for idx, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                section = line.lstrip("#").strip()
                units.append(
                    {
                        "kind": "entity",
                        "label": section or line[:120],
                        "text": line,
                        "line": idx,
                        "section": section,
                        "source": "doc_heading",
                    }
                )
                continue
            if line.startswith(("- ", "* ", "> ")) or any(
                token in line.lower() for token in ("must ", "should ", "requires ", "because ", "therefore ")
            ):
                units.append(
                    {
                        "kind": _classify_doc_line(line),
                        "label": line[:120],
                        "text": line,
                        "line": idx,
                        "section": section,
                        "source": "doc_line",
                    }
                )
        return units[:200]

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        if line.startswith(("class ", "def ", "function ", "export function ", "interface ", "type ")):
            units.append(
                {
                    "kind": "entity",
                    "label": line[:120],
                    "text": line,
                    "line": idx,
                    "section": rel,
                    "source": "code_symbol_line",
                }
            )
        elif any(token in low for token in ("todo", "fixme", "hack", "invariant", "must ", "should ")):
            units.append(
                {
                    "kind": "claim",
                    "label": line[:120],
                    "text": line,
                    "line": idx,
                    "section": rel,
                    "source": "code_comment_or_assertion",
                }
            )
    return units[:120]


def _merge_units(base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for unit in [*base, *extra]:
        key = (
            str(unit.get("kind") or ""),
            str(unit.get("text") or "").strip().lower(),
            int(unit.get("line") or 1),
        )
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(unit)
    return out


def _llm_units_for_file(
    root: Path,
    path: Path,
    *,
    provider_id: str | None,
    model_id: str | None,
) -> list[dict[str, Any]]:
    from apps.backend.infrastructure.extractor_client import extract_units_with_llm

    text = _read_text(path)
    if not text.strip():
        return []
    return extract_units_with_llm(
        text=text,
        file_path=path.relative_to(root).as_posix(),
        provider_id=provider_id,
        model_id=model_id,
    )


def build_workspace_knowledge_units(
    root: Path,
    *,
    max_files: int = 1000,
    extractor_backend: str = "deterministic",
    extractor_provider_id: str | None = None,
    extractor_model: str | None = None,
) -> list[tuple[str, list[dict[str, Any]]]]:
    out: list[tuple[str, list[dict[str, Any]]]] = []
    files_seen = 0
    backend = (extractor_backend or "deterministic").strip().lower()
    if backend not in ("deterministic", "llm", "hybrid"):
        backend = "deterministic"
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file() or not _is_candidate(path.relative_to(root)):
            continue
        files_seen += 1
        if files_seen > max_files:
            break
        try:
            det_units = [] if backend == "llm" else extract_knowledge_units_for_file(root, path)
            llm_units = (
                _llm_units_for_file(
                    root,
                    path,
                    provider_id=extractor_provider_id,
                    model_id=extractor_model,
                )
                if backend in ("llm", "hybrid")
                else []
            )
            units = _merge_units(det_units, llm_units)
        except (OSError, ValueError):
            continue
        if units:
            out.append((path.relative_to(root).as_posix(), units))
    return out

