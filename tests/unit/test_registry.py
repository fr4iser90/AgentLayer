"""
Registry scan/load tests (discovery, duplicates, extra dirs, validation, determinism).

Uses ``AGENT_TOOL_DIRS`` pointing at temp trees so the global registry can be
rescaned without mutating shipped ``tools/``. Each test restores the full tree
via :func:`reload_registry` after patching.

**Duplicates:** if two modules register the same function ``name``, the first file
in lexicographic ``rglob("*.py")`` order wins; the later registration is skipped
(see ``_register_module`` in ``registry.py``).

**Shipped integration** tests require ``httpx`` (full ``requirements.txt``); otherwise
they are skipped so minimal CI can still run the temp-dir cases.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import textwrap
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch


def _project_venv_ready() -> bool:
    """Shipped-tool scan executes tool modules; many need ``httpx`` and other deps from requirements.txt."""
    return importlib.util.find_spec("httpx") is not None

# ``registry`` imports ``db.log_tool_invocation``; tests must run without ``psycopg`` installed.
_db_mod_name = "src.infrastructure.db.db"
if _db_mod_name not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.log_tool_invocation = lambda *a, **k: None
    sys.modules[_db_mod_name] = _db_stub

from apps.backend.domain.plugin_system.capability_index import list_tools_without_capabilities
from apps.backend.domain.plugin_system.registry import (
    ToolRegistry,
    _iter_tool_py_files,
    reload_registry,
)


def _tool_function_names(reg: ToolRegistry) -> list[str]:
    out: list[str] = []
    for spec in reg.chat_tool_specs:
        fn = spec.get("function") if isinstance(spec, dict) else None
        if isinstance(fn, dict):
            n = fn.get("name")
            if isinstance(n, str) and n.strip():
                out.append(n.strip())
    return out


def _function_spec_has_basic_schema(spec: dict[str, Any]) -> bool:
    fn = spec.get("function") if isinstance(spec, dict) else None
    if not isinstance(fn, dict):
        return False
    params = fn.get("parameters")
    if not isinstance(params, dict):
        return False
    return params.get("type") == "object"


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class TestRegistryIterFiles(unittest.TestCase):
    def test_ignores_non_python_and_private_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skip.txt").write_text("x", encoding="utf-8")
            (root / "_private.py").write_text("x=1", encoding="utf-8")
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "ok.py").write_text(
                "HANDLERS={}\nTOOLS=[]\nTOOL_ID='x'\n", encoding="utf-8"
            )
            files = _iter_tool_py_files(root)
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "ok.py")


class TestRegistryTempScans(unittest.TestCase):
    """Isolated scans; each case ends with full-tree ``reload_registry``."""

    def tearDown(self) -> None:
        os.environ.pop("AGENT_TOOL_DIRS", None)
        log = logging.getLogger("src.domain.plugin_system.registry")
        prev = log.level
        log.setLevel(logging.CRITICAL)
        try:
            reload_registry("all")
        finally:
            log.setLevel(prev)

    def test_nested_module_loaded(self) -> None:
        mod = '''
        import json
        from typing import Any, Callable

        def nested_ping(arguments: dict[str, Any]) -> str:
            return json.dumps({"ok": True})

        HANDLERS = {"nested_ping": nested_ping}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "nested_ping",
                "TOOL_DESCRIPTION": "nested",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "nested_pkg"
        TOOL_CAPABILITIES = ("test.nested",)
        '''
        with TemporaryDirectory() as tmp:
            _write(Path(tmp), "deep/sub/nested_tool.py", mod)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                reg = reload_registry("all")
            names = _tool_function_names(reg)
            self.assertIn("nested_ping", names)

    def test_invalid_module_does_not_abort_scan(self) -> None:
        good = '''
        import json
        from typing import Any, Callable

        def good_tool(arguments: dict[str, Any]) -> str:
            return json.dumps({"ok": True})

        HANDLERS = {"good_tool": good_tool}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "good_tool",
                "TOOL_DESCRIPTION": "ok",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "good_pkg"
        TOOL_CAPABILITIES = ("test.good",)
        '''
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_text("this is not valid python !!!\n", encoding="utf-8")
            _write(root, "good_tool.py", good)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                log = logging.getLogger("src.domain.plugin_system.registry")
                prev = log.level
                log.setLevel(logging.CRITICAL)
                try:
                    reg = reload_registry("all")
                finally:
                    log.setLevel(prev)
            names = _tool_function_names(reg)
            self.assertIn("good_tool", names)

    def test_duplicate_tool_name_first_file_wins(self) -> None:
        first = '''
        import json
        from typing import Any, Callable

        def dup_name(arguments: dict[str, Any]) -> str:
            return json.dumps({"which": "first"})

        HANDLERS = {"dup_name": dup_name}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "dup_name",
                "TOOL_DESCRIPTION": "first",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "a"
        TOOL_CAPABILITIES = ("test.dup",)
        '''
        second = '''
        import json
        from typing import Any, Callable

        def dup_name(arguments: dict[str, Any]) -> str:
            return json.dumps({"which": "second"})

        HANDLERS = {"dup_name": dup_name}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "dup_name",
                "TOOL_DESCRIPTION": "second",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "b"
        TOOL_CAPABILITIES = ("test.dup",)
        '''
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "aaa_first.py", first)
            _write(root, "zzz_second.py", second)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                reg = reload_registry("all")
            out = reg.run_tool("dup_name", {})
            data = json.loads(out)
            self.assertEqual(data.get("which"), "first")

    def test_two_scan_roots_merge(self) -> None:
        a = '''
        import json
        from typing import Any, Callable
        def tool_a(arguments: dict[str, Any]) -> str:
            return json.dumps({"id": "a"})
        HANDLERS = {"tool_a": tool_a}
        TOOLS = [{"type": "function", "function": {
            "name": "tool_a", "TOOL_DESCRIPTION": "a",
            "parameters": {"type": "object", "properties": {}},
        }}]
        TOOL_ID = "pa"
        TOOL_CAPABILITIES = ("test.a",)
        '''
        b = '''
        import json
        from typing import Any, Callable
        def tool_b(arguments: dict[str, Any]) -> str:
            return json.dumps({"id": "b"})
        HANDLERS = {"tool_b": tool_b}
        TOOLS = [{"type": "function", "function": {
            "name": "tool_b", "TOOL_DESCRIPTION": "b",
            "parameters": {"type": "object", "properties": {}},
        }}]
        TOOL_ID = "pb"
        TOOL_CAPABILITIES = ("test.b",)
        '''
        with TemporaryDirectory() as t1, TemporaryDirectory() as t2:
            _write(Path(t1), "a.py", a)
            _write(Path(t2), "b.py", b)
            combined = f"{t1},{t2}"
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": combined}):
                reg = reload_registry("all")
            names = set(_tool_function_names(reg))
            self.assertIn("tool_a", names)
            self.assertIn("tool_b", names)

    def test_tool_without_capabilities_is_listed_unclassified(self) -> None:
        mod = '''
        import json
        from typing import Any, Callable

        def naked_tool(arguments: dict[str, Any]) -> str:
            return json.dumps({"ok": True})

        HANDLERS = {"naked_tool": naked_tool}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "naked_tool",
                "TOOL_DESCRIPTION": "no caps",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "naked"
        '''
        with TemporaryDirectory() as tmp:
            _write(Path(tmp), "naked.py", mod)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                reg = reload_registry("all")
            missing = list_tools_without_capabilities(reg.tools_meta)
            self.assertIn("naked_tool", missing)

    def test_manifest_specs_have_name_description_parameters(self) -> None:
        mod = '''
        import json
        from typing import Any, Callable

        def manifest_tool(arguments: dict[str, Any]) -> str:
            return json.dumps({"ok": True})

        HANDLERS = {"manifest_tool": manifest_tool}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "manifest_tool",
                "TOOL_DESCRIPTION": "desc",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            },
        }]
        TOOL_ID = "mf"
        TOOL_CAPABILITIES = ("test.manifest",)
        '''
        with TemporaryDirectory() as tmp:
            _write(Path(tmp), "mf.py", mod)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                reg = reload_registry("all")
            for spec in reg.chat_tool_specs:
                fn = spec.get("function")
                if not isinstance(fn, dict):
                    continue
                if fn.get("name") != "manifest_tool":
                    continue
                self.assertTrue((fn.get("TOOL_DESCRIPTION") or "").strip())
                self.assertTrue(_function_spec_has_basic_schema(spec))
                return
            self.fail("manifest_tool spec not found")

    def test_domain_qualified_handler_does_not_warn(self) -> None:
        first = '''
        import json
        from typing import Any, Callable

        def read_file(arguments: dict[str, Any]) -> str:
            return json.dumps({"which": "first"})

        HANDLERS = {"read_file": read_file}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "TOOL_DESCRIPTION": "first",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "first_read"
        '''
        second = '''
        import json
        from typing import Any, Callable

        def read_file(arguments: dict[str, Any]) -> str:
            return json.dumps({"which": "repository"})

        HANDLERS = {"read_file": read_file}
        TOOLS = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "TOOL_DESCRIPTION": "repo read",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        TOOL_ID = "repo_read"
        TOOL_DOMAIN = "repository"
        '''
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "aaa_first.py", first)
            _write(root, "zzz_repo.py", second)
            with patch.dict(os.environ, {"AGENT_TOOL_DIRS": tmp}):
                log = logging.getLogger("apps.backend.domain.plugin_system.registry")
                with patch.object(log, "warning", wraps=log.warning) as mock_warn:
                    reg = reload_registry("all")
            names = _tool_function_names(reg)
            self.assertIn("read_file", names)
            self.assertIn("repository.read_file", names)
            stray = [
                c
                for c in mock_warn.call_args_list
                if c.args and "without matching TOOLS entry" in str(c.args[0])
            ]
            self.assertEqual(stray, [])


@unittest.skipUnless(
    _project_venv_ready(),
    "install requirements.txt (httpx, …) to scan the full shipped tools/ tree",
)
class TestRegistryShipped(unittest.TestCase):
    """Full repo ``tools/`` + ``workflows/`` tree (no ``AGENT_TOOL_DIRS``)."""

    def setUp(self) -> None:
        os.environ.pop("AGENT_TOOL_DIRS", None)
        reload_registry("all")

    def test_loads_substantial_tool_set(self) -> None:
        reg = reload_registry("all")
        names = _tool_function_names(reg)
        self.assertGreater(len(names), 15)
        self.assertIn("list", names)

    def test_deterministic_order(self) -> None:
        reg1 = reload_registry("all")
        n1 = sorted(_tool_function_names(reg1))
        reg2 = reload_registry("all")
        n2 = sorted(_tool_function_names(reg2))
        self.assertEqual(n1, n2)

    def test_chat_specs_have_object_parameters(self) -> None:
        reg = reload_registry("all")
        bad: list[str] = []
        for spec in reg.chat_tool_specs:
            fn = spec.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name") or "?"
            params = fn.get("parameters")
            if not isinstance(params, dict) or params.get("type") != "object":
                bad.append(str(name))
        self.assertEqual(
            bad,
            [],
            msg=f"tools missing object parameters schema: {bad[:20]}",
        )


if __name__ == "__main__":
    unittest.main()
