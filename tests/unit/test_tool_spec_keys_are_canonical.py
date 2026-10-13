"""``description`` is the schema key; ``TOOL_*`` are module constants — never keys.

The plugin tree arrived (bulk import ``97bd82f7``, 2026-04-06) already describing a
tool under ``"TOOL_DESCRIPTION"`` — the module constant's name copied into the spec
key — and backend code grew reads for the same mangled spelling. That key means
nothing to a JSON-Schema consumer, and any code parsing an outside API for a field
called ``description`` looked under ``TOOL_DESCRIPTION`` instead, so those values
were silently ``None`` / ``""``.

Only ``openai_compat_http._openai_strict_tools`` mapped the key back, so the model kept seeing
a correct schema while every other consumer (OpenAPI export, admin UI, introspection tools,
external-API parsing) saw the broken one. Pinned here so the key cannot come back.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from apps.backend.domain.agent_runtime.tool_call_parsing import _CONTENT_META_TOP_LEVEL_ARG_KEYS
from apps.backend.domain.plugin_system.registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_TREES = ("apps/backend", "plugins", "scripts", "tests")
# That module exists to pin the back-compat mapping, so it has to name the old key.
EXEMPT = {Path("tests/unit/test_openai_compat_http.py")}
MANGLED = frozenset({"TOOL_DESCRIPTION", "TOOL_LABEL", "TOOL_TRIGGERS"})
# ``getattr(mod, "TOOL_DESCRIPTION")`` stays legal: reading the module constant is what it is.
_KEY_METHODS = frozenset({"get", "setdefault", "pop", "getlist"})


def _scan_violations() -> list[str]:
    out: list[str] = []
    for tree_root in SCANNED_TREES:
        for path in sorted((REPO_ROOT / tree_root).rglob("*.py")):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if Path(rel) in EXEMPT:
                continue
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Dict):
                    for key in node.keys:
                        if isinstance(key, ast.Constant) and key.value in MANGLED:
                            out.append(f"{rel}:{node.lineno} dict key {key.value!r}")
                elif isinstance(node, ast.Subscript):
                    if isinstance(node.slice, ast.Constant) and node.slice.value in MANGLED:
                        out.append(f"{rel}:{node.lineno} subscript {node.slice.value!r}")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in _KEY_METHODS and node.args:
                        first = node.args[0]
                        if isinstance(first, ast.Constant) and first.value in MANGLED:
                            out.append(f"{rel}:{node.lineno} {node.func.attr}() key {first.value!r}")
    return out


def test_no_module_constant_name_is_used_as_a_key():
    """Nothing in the backend or plugin tree may store or read a module-constant name as a key."""
    assert _scan_violations() == []


def _mangled_paths(obj: Any, path: str = "spec") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key in MANGLED:
                hits.append(f"{path}.{key}")
            hits.extend(_mangled_paths(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(_mangled_paths(item, f"{path}[{i}]"))
    return hits


def test_registered_tool_specs_describe_themselves_canonically():
    specs = get_registry().chat_tool_specs
    assert specs, "registry loaded no tool specs"
    findings: list[str] = []
    for spec in specs:
        fn = spec.get("function") if isinstance(spec, dict) else None
        name = str((fn or {}).get("name") or "?")
        if "description" not in (fn or {}):
            findings.append(f"{name}: function has no description key")
        findings.extend(_mangled_paths(spec, name))
    assert findings == []


def test_router_category_payloads_use_canonical_keys():
    reg = get_registry()
    cats = reg.list_router_categories_catalog()
    assert cats, "router catalog loaded no categories"
    for cat in cats:
        assert set(cat) == {"id", "label", "description", "tool_count"}
    rows = reg.list_router_category_tools_lite(cats[0]["id"])
    assert rows
    for row in rows:
        assert set(row) == {"name", "description"}


def test_meta_content_merge_lifts_the_description_argument():
    assert "description" in _CONTENT_META_TOP_LEVEL_ARG_KEYS
    assert "TOOL_DESCRIPTION" not in _CONTENT_META_TOP_LEVEL_ARG_KEYS


def test_brave_result_description_becomes_content(monkeypatch) -> None:
    """Brave names the snippet ``description``; it used to be read under the mangled key."""
    from plugins.tools.integrations.web_search.search import _normalize_brave

    data = {"web": {"results": [{"title": "T", "url": "https://e/x", "description": "snippet"}]}}
    results = _normalize_brave(data)["results"]
    assert results[0]["content"] == "snippet"


def test_weather_current_keeps_the_condition_description(monkeypatch) -> None:
    """OpenWeather names ``weather[0].description``; it used to come back ``None``."""
    import httpx

    from plugins.tools.integrations.weather import api as weather_api

    payload = {
        "name": "Berlin",
        "main": {"temp": 21.0},
        "weather": [{"id": 500, "main": "Rain", "description": "light rain"}],
    }

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return payload

    class _Client:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            return None

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *_exc: Any) -> bool:
            return False

        def get(self, *_a: Any, **_kw: Any) -> _Response:
            return _Response()

    monkeypatch.setattr(weather_api, "_api_key", lambda: "test-key")
    monkeypatch.setattr(
        weather_api,
        "httpx",
        type("HttpxStandIn", (), {"Client": _Client, "HTTPStatusError": httpx.HTTPStatusError}),
    )

    out = json.loads(weather_api.current({"location": "Berlin"}))
    assert out["ok"] is True
    assert out["weather_description"] == "light rain"
