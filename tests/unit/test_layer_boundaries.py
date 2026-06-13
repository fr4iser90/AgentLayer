"""Layer boundary checks — tool libs belong in plugins, not backend domain."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKEND_DOMAIN = _REPO / "apps" / "backend" / "domain"
_PLUGINS_TOOLS = _REPO / "plugins" / "tools"

_FORBIDDEN_BACKEND_DIRS = frozenset({
    "mail",
    "github",
    "tool_factory",
    "security_scan",
    "coding",
    "friends",
    "http_connector",
    "comms",
})
_FORBIDDEN_BACKEND_FILES = frozenset({"ssc_scan_artifact.py", "coding_plan_search_policy.py"})

_EXPECTED_PLUGIN_PATHS = (
    _PLUGINS_TOOLS / "integrations" / "mail" / "lib" / "providers.py",
    _PLUGINS_TOOLS / "integrations" / "github" / "lib" / "auth.py",
    _PLUGINS_TOOLS / "platform" / "tool_factory" / "common.py",
    _PLUGINS_TOOLS / "security" / "security_scan" / "common.py",
    _PLUGINS_TOOLS / "security" / "security_scan" / "artifact.py",
    _PLUGINS_TOOLS / "platform" / "shared" / "deferred_wait.py",
    _PLUGINS_TOOLS / "workspace" / "lib" / "common.py",
    _PLUGINS_TOOLS / "workspace" / "lib" / "index_lib.py",
    _PLUGINS_TOOLS / "integrations" / "http" / "lib" / "request.py",
    _PLUGINS_TOOLS / "integrations" / "friends" / "lib" / "common.py",
    _PLUGINS_TOOLS / "integrations" / "messaging" / "lib" / "outbound.py",
)


def test_backend_domain_has_no_tool_integration_packages() -> None:
    for name in _FORBIDDEN_BACKEND_DIRS:
        path = _BACKEND_DOMAIN / name
        assert not path.exists(), f"{path} is a domain violation — colocate under plugins/tools"


def test_backend_domain_has_no_tool_artifact_modules() -> None:
    for name in _FORBIDDEN_BACKEND_FILES:
        path = _BACKEND_DOMAIN / name
        assert not path.exists(), f"{path} is a domain violation — colocate under plugins/tools"


def test_tool_libs_live_under_plugins() -> None:
    missing = [str(p.relative_to(_REPO)) for p in _EXPECTED_PLUGIN_PATHS if not p.is_file()]
    assert not missing, f"Expected plugin tool libs missing: {missing}"


def test_async_wait_stays_platform_generic() -> None:
    """Generic wait loop is platform infra, not a tool domain package."""
    path = _BACKEND_DOMAIN / "async_wait.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "security_scan" not in text.lower()
    assert "poll_tool" not in text
