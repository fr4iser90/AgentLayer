"""Unit tests for volume npm coding-runtime package helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.agent_runtime.external_runtimes import coding_runtime_packages as mod


def test_resolve_runtime_binary_prefers_volume_prefix(tmp_path: Path, monkeypatch) -> None:
    prefix = tmp_path / "npm-global"
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True)
    qwen = bin_dir / "qwen"
    qwen.write_text("#!/bin/sh\necho 1\n", encoding="utf-8")
    qwen.chmod(0o755)

    monkeypatch.setattr(mod, "npm_global_prefix", lambda: prefix)
    monkeypatch.setattr(mod, "npm_global_bin_dir", lambda: bin_dir)

    assert mod.resolve_runtime_binary("qwen_code") == str(qwen)


def test_install_rejects_unknown_runtime() -> None:
    out = mod.install_coding_runtime_package("nope")
    assert out["ok"] is False
    assert "unknown" in (out.get("error") or "").lower()


def test_install_rejects_bad_version() -> None:
    out = mod.install_coding_runtime_package("qwen_code", version="latest;rm -rf /")
    assert out["ok"] is False
    assert "invalid version" in (out.get("error") or "").lower()


def test_install_runs_npm_with_prefix(tmp_path: Path, monkeypatch) -> None:
    prefix = tmp_path / "npm-global"
    home_root = tmp_path / "rt"
    monkeypatch.setattr(mod, "npm_global_prefix", lambda: prefix)
    monkeypatch.setattr(mod, "npm_global_bin_dir", lambda: prefix / "bin")
    monkeypatch.setattr(mod, "external_runtime_home_dir", lambda: home_root)
    monkeypatch.setattr(mod, "resolve_runtime_binary", lambda rid: str(prefix / "bin" / "qwen"))
    monkeypatch.setattr(mod, "probe_binary_version", lambda binary: "0.23.3")

    proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with (
        patch.object(mod.shutil, "which", return_value="/usr/bin/npm"),
        patch.object(mod.subprocess, "run", return_value=proc) as run,
    ):
        out = mod.install_coding_runtime_package("qwen_code", version="latest")

    assert out["ok"] is True
    cmd = run.call_args[0][0]
    assert cmd[0] == "/usr/bin/npm"
    assert "install" in cmd
    assert "-g" in cmd
    assert "--prefix" in cmd
    assert "@qwen-code/qwen-code@latest" in cmd
    env = run.call_args.kwargs["env"]
    assert env["HOME"] == str(home_root / "npm-home")
    assert env["npm_config_cache"] == str(home_root / "npm-home" / ".npm")


def test_list_npm_package_versions_builds_select_options(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "npm_global_prefix", lambda: tmp_path / "npm-global")
    monkeypatch.setattr(mod, "external_runtime_home_dir", lambda: tmp_path)

    def fake_run(cmd, **_kwargs):
        proc = MagicMock(returncode=0, stderr="")
        if "dist-tags" in cmd:
            proc.stdout = '{"latest":"0.2.0-rc.2","next":"0.3.0-alpha.1"}'
        elif "versions" in cmd:
            proc.stdout = '["0.1.0","0.2.0-rc.1","0.2.0-rc.2"]'
        else:
            proc.stdout = "{}"
        return proc

    with (
        patch.object(mod.shutil, "which", return_value="/usr/bin/npm"),
        patch.object(mod.subprocess, "run", side_effect=fake_run),
    ):
        out = mod.list_npm_package_versions("deepseek_harness")

    assert out["ok"] is True
    values = [o["value"] for o in out["options"]]
    assert values[0] == "latest"
    assert "next" in values
    assert "0.2.0-rc.2" in values
    assert out["default"] == "latest"


def test_uninstall_no_volume_package_when_only_path(monkeypatch, tmp_path: Path) -> None:
    prefix = tmp_path / "npm-global"
    (prefix / "bin").mkdir(parents=True)
    monkeypatch.setattr(mod, "npm_global_prefix", lambda: prefix)
    monkeypatch.setattr(mod, "npm_global_bin_dir", lambda: prefix / "bin")
    monkeypatch.setattr(mod, "external_runtime_home_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "resolve_runtime_binary", lambda rid: "/usr/local/bin/qwen")
    monkeypatch.setattr(mod, "volume_binary_installed", lambda rid: False)
    monkeypatch.setattr(
        mod,
        "runtime_package_status",
        lambda rid: {"id": rid, "installed": True, "volume_installed": False, "source": "image"},
    )

    out = mod.uninstall_coding_runtime_package("qwen_code")
    assert out["ok"] is False
    assert "image" in (out.get("error") or "").lower() or "path" in (out.get("error") or "").lower()


def test_dsh_runtime_enabled_effective_override() -> None:
    # Import order avoids circular init between operator_settings <-> readers.
    import apps.backend.infrastructure.settings.operator_settings  # noqa: F401
    import apps.backend.infrastructure.settings.operator_settings_readers as readers
    from apps.backend.infrastructure.platform import config_external_runtimes as crt

    with (
        patch.object(crt, "DSH_RUNTIME_ENABLED", True),
        patch.object(readers, "dsh_runtime_enabled_override", return_value=False),
    ):
        assert crt.dsh_runtime_enabled_effective() is False
