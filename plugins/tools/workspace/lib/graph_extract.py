"""Extract relationships (calls, extends, implements) from tree-sitter ASTs."""

from __future__ import annotations

import logging
from typing import Any

from plugins.tools.workspace.lib.index_lib import Relationship, Symbol

logger = logging.getLogger(__name__)

try:
    from tree_sitter import Node, Tree
    _HAS_TS = True
except ImportError:
    _HAS_TS = False


def extract_relationships(
    tree: Any,
    source: bytes,
    language: str,
    symbols: list[Symbol],
) -> list[Relationship]:
    if not _HAS_TS or tree is None or tree.root_node is None:
        return []

    rels: list[Relationship] = []
    func_names = {s.name for s in symbols if s.kind == "function"}
    class_names = {s.name for s in symbols if s.kind == "class"}
    known_names = func_names | class_names

    _extract_calls(tree.root_node, language, symbols, known_names, rels)
    _extract_inheritance(tree.root_node, language, rels)

    return rels


def _enclosing_function(node: Any, language: str) -> str | None:
    """Walk up the AST to find the enclosing function/method name."""
    fn_types = _FN_NODE_TYPES.get(language, set())
    current = node.parent
    while current is not None:
        if current.type in fn_types:
            for child in current.children:
                if child.type in ("identifier", "property_identifier", "field_identifier"):
                    try:
                        return child.text.decode("utf-8")
                    except Exception:
                        pass
        current = current.parent
    return None


_FN_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "go": {"function_declaration", "method_declaration"},
    "rust": {"function_item"},
    "java": {"method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
    "c_sharp": {"method_declaration"},
}

_CALL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "go": {"call_expression"},
    "rust": {"call_expression"},
    "java": {"method_invocation"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
    "c_sharp": {"invocation_expression"},
}

_CLASS_NODE_TYPES: dict[str, set[str]] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "go": set(),
    "rust": set(),
    "java": {"class_declaration"},
    "c": set(),
    "cpp": {"class_specifier"},
    "c_sharp": {"class_declaration"},
}


def _extract_callee_name(node: Any, language: str) -> str | None:
    """Extract the callee name from a call node."""
    if language == "python":
        fn_node = _child_by_field(node, "function")
        if fn_node is None:
            return None
        if fn_node.type == "identifier":
            return _node_text(fn_node)
        if fn_node.type == "attribute":
            attr = _child_by_field(fn_node, "attribute")
            if attr is not None:
                return _node_text(attr)
        return None

    if language in ("javascript", "typescript"):
        fn_node = _child_by_field(node, "function")
        if fn_node is None:
            return None
        if fn_node.type == "identifier":
            return _node_text(fn_node)
        if fn_node.type == "member_expression":
            prop = _child_by_field(fn_node, "property")
            if prop is not None:
                return _node_text(prop)
        return None

    if language == "go":
        fn_node = _child_by_field(node, "function")
        if fn_node is None:
            return None
        if fn_node.type == "identifier":
            return _node_text(fn_node)
        if fn_node.type == "selector_expression":
            field = _child_by_field(fn_node, "field")
            if field is not None:
                return _node_text(field)
        return None

    if language == "java":
        name_node = _child_by_field(node, "name")
        if name_node is not None:
            return _node_text(name_node)
        return None

    if language == "rust":
        fn_node = _child_by_field(node, "function")
        if fn_node is None:
            return None
        if fn_node.type == "identifier":
            return _node_text(fn_node)
        if fn_node.type == "scoped_identifier":
            name = _child_by_field(fn_node, "name")
            if name is not None:
                return _node_text(name)
        if fn_node.type == "field_expression":
            field = _child_by_field(fn_node, "field")
            if field is not None:
                return _node_text(field)
        return None

    if language in ("c", "cpp"):
        fn_node = _child_by_field(node, "function")
        if fn_node is None:
            return None
        if fn_node.type == "identifier":
            return _node_text(fn_node)
        return None

    if language == "c_sharp":
        for child in node.children:
            if child.type == "identifier":
                return _node_text(child)
            if child.type == "member_access_expression":
                name = _child_by_field(child, "name")
                if name is not None:
                    return _node_text(name)
        return None

    return None


def _extract_calls(
    root: Any,
    language: str,
    symbols: list[Symbol],
    known_names: set[str],
    rels: list[Relationship],
) -> None:
    call_types = _CALL_NODE_TYPES.get(language, set())
    if not call_types:
        return

    seen: set[tuple[str, str]] = set()

    def visit(node: Any) -> None:
        if node.type in call_types:
            callee = _extract_callee_name(node, language)
            if callee and callee in known_names:
                caller = _enclosing_function(node, language)
                if caller and caller != callee:
                    key = (caller, callee)
                    if key not in seen:
                        seen.add(key)
                        line = node.start_point[0] + 1
                        rels.append(Relationship(
                            kind="calls",
                            source=caller,
                            target=callee,
                            line=line,
                        ))
        for child in node.children:
            visit(child)

    visit(root)


def _extract_inheritance(root: Any, language: str, rels: list[Relationship]) -> None:
    class_types = _CLASS_NODE_TYPES.get(language, set())
    if not class_types:
        return

    def visit(node: Any) -> None:
        if node.type in class_types:
            _extract_bases_for_class(node, language, rels)
        for child in node.children:
            visit(child)

    visit(root)


def _extract_bases_for_class(node: Any, language: str, rels: list[Relationship]) -> None:
    class_name: str | None = None
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            class_name = _node_text(child)
            break
    if not class_name:
        return

    line = node.start_point[0] + 1

    if language == "python":
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        base = _node_text(arg)
                        if base and base != class_name:
                            rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))
                    elif arg.type == "attribute":
                        base = _node_text(arg)
                        if base and base != class_name:
                            rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))

    elif language in ("javascript", "typescript"):
        for child in node.children:
            if child.type == "class_heritage":
                for clause in child.children:
                    if clause.type == "extends_clause":
                        for val in clause.children:
                            if val.type in ("identifier", "type_identifier"):
                                base = _node_text(val)
                                if base and base != class_name:
                                    rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))
                    elif clause.type == "implements_clause":
                        for val in clause.children:
                            if val.type in ("identifier", "type_identifier"):
                                iface = _node_text(val)
                                if iface and iface != class_name:
                                    rels.append(Relationship(kind="implements", source=class_name, target=iface, line=line))

    elif language == "java":
        for child in node.children:
            if child.type == "superclass":
                for val in child.children:
                    if val.type == "type_identifier":
                        base = _node_text(val)
                        if base:
                            rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))
            elif child.type == "super_interfaces":
                for val in child.children:
                    if val.type == "type_list":
                        for iface_node in val.children:
                            if iface_node.type == "type_identifier":
                                iface = _node_text(iface_node)
                                if iface:
                                    rels.append(Relationship(kind="implements", source=class_name, target=iface, line=line))

    elif language == "c_sharp":
        for child in node.children:
            if child.type == "base_list":
                for val in child.children:
                    if val.type in ("identifier", "type_identifier", "generic_name"):
                        base = _node_text(val)
                        if base and base != class_name:
                            rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))

    elif language == "cpp":
        for child in node.children:
            if child.type == "base_class_clause":
                for val in child.children:
                    if val.type == "type_identifier":
                        base = _node_text(val)
                        if base and base != class_name:
                            rels.append(Relationship(kind="extends", source=class_name, target=base, line=line))


def _child_by_field(node: Any, field_name: str) -> Any:
    try:
        return node.child_by_field_name(field_name)
    except Exception:
        return None


def _node_text(node: Any) -> str:
    try:
        return node.text.decode("utf-8")
    except Exception:
        return ""


def resolve_import_relationships(file_entry: Any, indexed_paths: set[str]) -> list[dict[str, str | int]]:
    """Turn raw import strings into IMPORTS edges against known indexed file paths."""
    from pathlib import PurePosixPath

    rels: list[dict[str, str | int]] = []
    lang = file_entry.language

    for imp in file_entry.imports:
        candidates: list[str] = []
        if lang == "python":
            mod_path = imp.replace(".", "/")
            candidates = [f"{mod_path}.py", f"{mod_path}/__init__.py"]
        elif lang in ("javascript", "typescript"):
            clean = imp.strip("'\"")
            if clean.startswith("."):
                base_dir = str(PurePosixPath(file_entry.path).parent)
                resolved = str(PurePosixPath(base_dir, clean))
                for ext in (".ts", ".tsx", ".js", ".jsx"):
                    candidates.append(resolved + ext)
                candidates.append(resolved + "/index.ts")
                candidates.append(resolved + "/index.js")

        for cand in candidates:
            norm = cand.lstrip("/")
            if norm in indexed_paths and norm != file_entry.path:
                rels.append({
                    "kind": "imports",
                    "source": file_entry.path,
                    "target": norm,
                    "line": 0,
                })
                break

    return rels
