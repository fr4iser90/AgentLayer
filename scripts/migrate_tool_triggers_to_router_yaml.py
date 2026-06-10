#!/usr/bin/env python3
"""One-shot: move TOOL_TRIGGERS from plugin .py files to co-located *.router.yaml."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "plugins" / "tools"

YAML_HEADER = """# Co-located router phrases for {stem}.py — locale keys are authoring-only.
domain: {domain}
phrases:
  en:
"""


def _literal(node: ast.AST | None) -> object | None:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _domain_from_source(src: str) -> str | None:
    m = re.search(r'^TOOL_DOMAIN\s*=\s*["\']([^"\']+)["\']', src, re.M)
    if m:
        return m.group(1).strip().lower()
    if "ssc_domain_attrs" in src or '_attrs["TOOL_DOMAIN"]' in src:
        return "security_scan"
    return None


def _module_constants(path: Path) -> tuple[str | None, tuple[str, ...] | None, bool]:
    """Return (TOOL_DOMAIN, TOOL_TRIGGERS tuple or None, has_TOOL_TRIGGERS_name)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    domain = _domain_from_source(src)
    triggers: tuple[str, ...] | None = None
    has_triggers_name = False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "TOOL_DOMAIN" and domain is None:
                        v = _literal(node.value)
                        if isinstance(v, str) and v.strip():
                            domain = v.strip().lower()
                    elif target.id == "TOOL_TRIGGERS":
                        has_triggers_name = True
                        v = _literal(node.value)
                        if isinstance(v, (list, tuple)):
                            triggers = tuple(str(x).strip().lower() for x in v if str(x).strip())
                        elif isinstance(v, str) and v.strip():
                            triggers = (v.strip().lower(),)
                        else:
                            triggers = ()
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "TOOL_DOMAIN" and domain is None:
                v = _literal(node.value)
                if isinstance(v, str) and v.strip():
                    domain = v.strip().lower()
            elif node.target.id == "TOOL_TRIGGERS":
                has_triggers_name = True
                v = _literal(node.value)
                if isinstance(v, (list, tuple)):
                    triggers = tuple(str(x).strip().lower() for x in v if str(x).strip())
                elif isinstance(v, str) and v.strip():
                    triggers = (v.strip().lower(),)
                else:
                    triggers = ()

    return domain, triggers, has_triggers_name


def _tool_id_fallback(path: Path) -> str | None:
    src = path.read_text(encoding="utf-8")
    m = re.search(r'^TOOL_ID\s*=\s*["\']([^"\']+)["\']', src, re.M)
    return m.group(1).strip().lower() if m else None


def _yaml_lines(phrases: tuple[str, ...]) -> str:
    if not phrases:
        return "    []\n"
    return "".join(f"    - {p}\n" for p in phrases)


def _replace_tool_triggers_in_source(src: str) -> str:
    """Replace TOOL_TRIGGERS assignment with empty tuple + comment."""
    comment = "# Router phrases: co-located {stem}.router.yaml (all locales unioned at load)."
    # Annotated empty tuple (read_file style)
    pat_ann = re.compile(
        r"^TOOL_TRIGGERS\s*:\s*[^\n=]+\=\s*\([^)]*\)\s*$",
        re.M,
    )
    if pat_ann.search(src):
        return pat_ann.sub("TOOL_TRIGGERS: tuple[str, ...] = ()", src, count=1)

    # Multi-line or single-line tuple/string assign
    pat = re.compile(
        r"^TOOL_TRIGGERS\s*=\s*(?:\([^)]*\)|\([^)]*\n[^)]*\)|\"[^\"]*\"|'[^']*')\s*$",
        re.M | re.S,
    )
    # Better: match from TOOL_TRIGGERS = to closing paren of top-level assign
    pat2 = re.compile(
        r"^TOOL_TRIGGERS\s*=\s*\([\s\S]*?\)\s*$",
        re.M,
    )
    if pat2.search(src):
        return pat2.sub("TOOL_TRIGGERS: tuple[str, ...] = ()", src, count=1)

    pat3 = re.compile(r'^TOOL_TRIGGERS\s*=\s*\(\s*\)\s*$', re.M)
    if pat3.search(src):
        return pat3.sub("TOOL_TRIGGERS: tuple[str, ...] = ()", src, count=1)

    pat4 = re.compile(r'^TOOL_TRIGGERS\s*=\s*"[^"]*"\s*$', re.M)
    if pat4.search(src):
        return pat4.sub("TOOL_TRIGGERS: tuple[str, ...] = ()", src, count=1)

    pat5 = re.compile(r"^TOOL_TRIGGERS\s*=\s*'[^']*'\s*$", re.M)
    if pat5.search(src):
        return pat5.sub("TOOL_TRIGGERS: tuple[str, ...] = ()", src, count=1)

    return src


def _insert_comment_after_domain(src: str, stem: str) -> str:
    needle = "TOOL_TRIGGERS: tuple[str, ...] = ()"
    comment = f"# Router phrases: co-located {stem}.router.yaml (all locales unioned at load)."
    if comment in src:
        return src
    if needle in src:
        return src.replace(needle, f"{comment}\n{needle}", 1)
    return src


def migrate_file(py_path: Path, *, dry_run: bool = False) -> str | None:
    if py_path.name.startswith("_"):
        return None
    yaml_path = py_path.with_name(f"{py_path.stem}.router.yaml")
    if not py_path.is_file():
        return None

    src = py_path.read_text(encoding="utf-8")
    if "HANDLERS" not in src and "TOOLS" not in src:
        return None

    domain, triggers, has_triggers = _module_constants(py_path)
    if not domain:
        return f"skip {py_path.relative_to(ROOT)}: no TOOL_DOMAIN"

    if yaml_path.exists() and not has_triggers:
        return None  # already migrated (e.g. read_file)

    phrase_list: list[str] = []
    if triggers:
        phrase_list = list(triggers)
    if not phrase_list:
        tid = _tool_id_fallback(py_path)
        if tid:
            phrase_list = [tid]

    if yaml_path.exists():
        # Already migrated — still patch .py if TOOL_TRIGGERS remain
        if has_triggers and triggers:
            pass
        elif has_triggers:
            new_src = _replace_tool_triggers_in_source(src)
            new_src = _insert_comment_after_domain(new_src, py_path.stem)
            if new_src != src and not dry_run:
                py_path.write_text(new_src, encoding="utf-8")
            return f"patch {py_path.relative_to(ROOT)}"
        return None
    else:
        body = YAML_HEADER.format(stem=py_path.stem, domain=domain) + _yaml_lines(tuple(phrase_list))
        if dry_run:
            return f"write {yaml_path.relative_to(ROOT)} ({len(phrase_list)} phrases)"
        yaml_path.write_text(body, encoding="utf-8")

    if has_triggers or not yaml_path.exists():
        new_src = _replace_tool_triggers_in_source(src) if has_triggers else src
        if has_triggers:
            new_src = _insert_comment_after_domain(new_src, py_path.stem)
        if new_src != src:
            if dry_run:
                return f"patch {py_path.relative_to(ROOT)}"
            py_path.write_text(new_src, encoding="utf-8")

    return f"ok {py_path.relative_to(ROOT)}"


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    results: list[str] = []
    for py_path in sorted(TOOLS_ROOT.rglob("*.py")):
        if py_path.stem.endswith(".router"):
            continue
        msg = migrate_file(py_path, dry_run=dry_run)
        if msg:
            results.append(msg)

    for line in results:
        print(line)
    print(f"\n{len(results)} actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
