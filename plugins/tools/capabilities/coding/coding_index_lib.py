"""Fast code index with tree-sitter symbol extraction.

Supports: Python, JavaScript, TypeScript, Go, Rust, Java, C, C++.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from tree_sitter import Node, Parser, Query, Tree
    import tree_sitter_language_pack as tslp
    _HAS_TS = True
except ImportError:
    try:
        from tree_sitter import Node, Parser, Query, Tree
        import tree_sitter_language_pack
        _HAS_TS = True
    except ImportError:
        _HAS_TS = False

_SUPPORTED_LANGUAGES = {
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

_QUERY_SYMBOLS = {
    "python": """
        (function_definition name: (identifier) @name) @fn
        (class_definition name: (identifier) @name) @cls
        (import_statement name: (dotted_name) @name) @imp
        (import_from_statement module_name: (dotted_name) @name) @imp
    """,
    "javascript": """
        (function_declaration name: (identifier) @name) @fn
        (class_declaration name: (identifier) @name) @cls
        (method_definition name: (property_identifier) @name) @fn
        (import_statement source: (string) @name) @imp
        (import_specifier name: (identifier) @name) @imp
    """,
    "typescript": """
        (function_declaration name: (identifier) @name) @fn
        (class_declaration name: (identifier) @name) @cls
        (method_definition name: (property_identifier) @name) @fn
        (interface_declaration name: (type_identifier) @name) @cls
        (type_alias_declaration name: (type_identifier) @name) @cls
        (import_statement source: (string) @name) @imp
        (import_specifier name: (identifier) @name) @imp
    """,
    "go": """
        (function_declaration name: (identifier) @name) @fn
        (method_declaration name: (field_identifier) @name) @fn
        (type_declaration (type_spec name: (type_identifier) @name)) @cls
        (import_declaration (import_spec path: (interpreted_string_literal) @name)) @imp
    """,
    "rust": """
        (function_item name: (identifier) @name) @fn
        (struct_item name: (type_identifier) @name) @cls
        (enum_item name: (type_identifier) @name) @cls
        (trait_item name: (type_identifier) @name) @cls
        (use_declaration argument: (scoped_identifier path: (identifier)? @name)) @imp
    """,
    "java": """
        (class_declaration name: (identifier) @name) @cls
        (interface_declaration name: (identifier) @name) @cls
        (method_declaration name: (identifier) @name) @fn
        (import_declaration name: (scoped_identifier) @name) @imp
    """,
    "c": """
        (function_definition declarator: (function_declarator declarator: (identifier) @name)) @fn
        (type_definition declarator: (type_identifier) @name) @cls
        (struct_specifier name: (type_identifier) @name) @cls
    """,
    "cpp": """
        (function_definition declarator: (function_declarator declarator: (identifier) @name)) @fn
        (class_specifier name: (type_identifier) @name) @cls
        (struct_specifier name: (type_identifier) @name) @cls
        (namespace_definition name: (identifier) @name) @ns
    """,
    "c_sharp": """
        (class_declaration name: (identifier) @name) @cls
        (method_declaration name: (identifier) @name) @fn
        (interface_declaration name: (identifier) @name) @cls
        (using_directive name: (qualified_name) @name) @imp
    """,
}


@dataclass
class Symbol:
    kind: str  # function, class, import, namespace
    name: str
    line: int
    col: int
    end_line: int
    end_col: int
    parent: str = ""
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "parent": self.parent,
            "signature": self.signature,
        }


@dataclass
class FileEntry:
    path: str
    language: str
    size_bytes: int
    line_count: int
    sha256: str
    mtime: float
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "sha256": self.sha256,
            "mtime": self.mtime,
            "symbol_count": len(self.symbols),
            "import_count": len(self.imports),
        }


def _detect_language(file_path: Path) -> str | None:
    return _SUPPORTED_LANGUAGES.get(file_path.suffix.lower())


def _parse_tree(source: bytes, language: str) -> Tree | None:
    if not _HAS_TS:
        return None
    try:
        import tree_sitter_language_pack as tslp
        
        lang = tslp.get_language(language)
        if lang is None:
            return None
        
        parser = Parser(lang)
        result = parser.parse(source)
        
        if result is None:
            return None
            
        return result
        
    except Exception:
        return None


def _extract_symbols(tree: Tree, source: bytes, language: str) -> tuple[list[Symbol], list[str]]:
    if tree is None or tree.root_node is None:
        return [], []
    
    if language not in _QUERY_SYMBOLS:
        return [], []
    
    query = None
    try:
        import tree_sitter_language_pack as tslp
        
        lang = tslp.get_language(language)
        if lang is None:
            return [], []
        
        try:
            query = lang.query(_QUERY_SYMBOLS[language])
        except:
            from tree_sitter import Query as TSQuery
            query = TSQuery(lang, _QUERY_SYMBOLS[language])
    except:
        return [], []
    
    symbols: list[Symbol] = []
    imports: list[str] = []
    text = source.decode("utf-8", errors="replace")
    lines = text.split('\n')
    
    try:
        captures = query.captures(tree.root_node)
    except:
        captures = []
    
    if not captures:
        try:
            def walk(node):
                syms = []
                imps = []
                ntype = node.type
                
                if language == "python":
                    if ntype == "function_definition":
                        for child in node.children:
                            if child.type == "identifier":
                                name = child.text.decode("utf-8")
                                sr = node.start_point
                                er = node.end_point
                                sig = lines[sr[0]].strip()[:200] if sr[0] < len(lines) else ""
                                syms.append(Symbol(
                                    kind="function", name=name, line=sr[0]+1, col=sr[1]+1,
                                    end_line=er[0]+1, end_col=er[1]+1, parent="", signature=sig
                                ))
                                break
                    elif ntype == "class_definition":
                        for child in node.children:
                            if child.type == "identifier":
                                name = child.text.decode("utf-8")
                                sr = node.start_point
                                er = node.end_point
                                syms.append(Symbol(
                                    kind="class", name=name, line=sr[0]+1, col=sr[1]+1,
                                    end_line=er[0]+1, end_col=er[1]+1, parent="", signature=""
                                ))
                                break
                    elif ntype in ("import_statement", "import_from_statement"):
                        for child in node.children:
                            if child.type == "dotted_name":
                                name = child.text.decode("utf-8")
                                imps.append(name)
                                break
                            elif child.type == "module":
                                name = child.text.decode("utf-8")
                                imps.append(name)
                
                for child in node.children:
                    c_syms, c_imps = walk(child)
                    syms.extend(c_syms)
                    imps.extend(c_imps)
                return syms, imps
            
            syms, imps = walk(tree.root_node)
            logger.debug("walk fallback: %d symbols, %d imports", len(syms), len(imps))
            return syms, imps
            
        except Exception as e:
            logger.debug("walk fallback failed: %s", e)
            return [], []
    
    kind_map = {"fn": "function", "cls": "class", "imp": "import", "ns": "namespace"}
    for node, capture_name in captures:
        name_node = None
        if capture_name == "name":
            name_node = node
        if name_node is None:
            continue
        
        try:
            name = name_node.text.decode("utf-8")
        except:
            continue
        
        kind = kind_map.get(capture_name, "unknown")
        sr = node.start_point
        er = node.end_point
        sig = ""
        if kind == "function" and sr[0] < len(lines):
            sig = lines[sr[0]].strip()[:200]
        
        if kind == "import":
            imports.append(name)
        
        symbols.append(Symbol(
            kind=kind,
            name=name,
            line=sr[0] + 1,
            col=sr[1] + 1,
            end_line=er[0] + 1,
            end_col=er[1] + 1,
            parent="",
            signature=sig,
        ))
    
    return symbols, imports


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        data = path.read_bytes()
        h.update(data)
    except OSError:
        return ""
    return h.hexdigest()


class CodeIndex:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._files: dict[str, FileEntry] = {}
        self._symbol_index: dict[str, list[Symbol]] = {}
        self._last_scan: float = 0.0

    def index_file(self, file_path: Path, root: Path) -> FileEntry | None:
        try:
            rel = str(file_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            return None
        lang = _detect_language(file_path)
        if lang is None:
            return None
        try:
            stat = file_path.stat()
            size = stat.st_size
            mtime = stat.st_mtime
        except OSError:
            return None
        sha = _file_sha256(file_path)
        with self._lock:
            existing = self._files.get(rel)
            if existing and existing.sha256 == sha:
                return existing
        try:
            source = file_path.read_bytes()
        except OSError:
            return None
        tree = _parse_tree(source, lang)
        symbols, imports = _extract_symbols(tree, source, lang) if tree else ([], [])
        line_count = source.count(b"\n") + (1 if source and not source.endswith(b"\n") else 0)
        entry = FileEntry(
            path=rel,
            language=lang,
            size_bytes=size,
            line_count=line_count,
            sha256=sha,
            mtime=mtime,
            symbols=symbols,
            imports=imports,
        )
        with self._lock:
            self._files[rel] = entry
            for sym in symbols:
                self._symbol_index.setdefault(sym.name, []).append(sym)
        return entry

    def scan(self, root: Path, max_files: int = 5000) -> dict[str, int]:
        stats: dict[str, int] = {"scanned": 0, "errors": 0, "skipped": 0}
        root_r = root.resolve()
        
        _SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".pytest_cache", ".mypy_cache", ".tox"}
        
        def iter_files() -> list[Path]:
            files: list[Path] = []
            for ext, lang in _SUPPORTED_LANGUAGES.items():
                for fp in root_r.rglob(f"*{ext}"):
                    skip = False
                    for part in fp.parts:
                        if part.startswith(".") or part in _SKIP_DIRS:
                            skip = True
                            break
                    if not skip:
                        files.append(fp)
            return files
        
        files_to_scan = sorted(set(iter_files()))[:max_files]
        for fp in files_to_scan:
            try:
                result = self.index_file(fp, root)
                if result:
                    stats["scanned"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                stats["errors"] += 1
        with self._lock:
            self._last_scan = time.time()
        return stats

    def lookup_symbol(self, name: str) -> list[dict[str, Any]]:
        with self._lock:
            syms = self._symbol_index.get(name, [])
        return [s.to_dict() for s in syms]

    def search_symbols(self, query: str, kind: str | None = None) -> list[dict[str, Any]]:
        ql = query.lower()
        results: list[dict[str, Any]] = []
        with self._lock:
            for name, syms in self._symbol_index.items():
                if ql in name.lower():
                    for s in syms:
                        if kind is None or s.kind == kind:
                            d = s.to_dict()
                            d["file"] = next(
                                (f.path for f in self._files.values() if s in f.symbols),
                                "",
                            )
                            results.append(d)
        return results[:200]

    def get_file(self, path: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._files.get(path)
        if entry is None:
            return None
        return {
            **entry.to_dict(),
            "symbols": [s.to_dict() for s in entry.symbols],
            "imports": entry.imports,
        }

    def list_files(self, language: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._files.values())
        if language:
            entries = [e for e in entries if e.language == language]
        return [e.to_dict() for e in sorted(entries, key=lambda e: e.path)]

    @property
    def last_scan(self) -> float:
        with self._lock:
            return self._last_scan

    @property
    def file_count(self) -> int:
        with self._lock:
            return len(self._files)

    @property
    def symbol_count(self) -> int:
        with self._lock:
            return sum(len(e.symbols) for e in self._files.values())


_index = CodeIndex()


def get_index() -> CodeIndex:
    return _index
