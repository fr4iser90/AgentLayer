"""Install / update / probe npm coding harnesses under the external-runtime volume.

Uses ``npm install -g --prefix {EXTERNAL_RUNTIME_HOME}/npm-global`` so installs work
inside Docker without writing ``/usr/local``. Adapters resolve binaries from that prefix
first, then fall back to PATH / image-baked globals.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.backend.infrastructure.platform.config_external_runtimes import external_runtime_home_dir

logger = logging.getLogger(__name__)

RUNTIME_ID_QWEN = "qwen_code"
RUNTIME_ID_DSH = "deepseek_harness"

_VERSION_RE = re.compile(r"[@/]v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?)")


@dataclass(frozen=True)
class CodingRuntimePackage:
    runtime_id: str
    npm_package: str
    bin_name: str
    label: str
    docs_url: str


CODING_RUNTIME_PACKAGES: dict[str, CodingRuntimePackage] = {
    RUNTIME_ID_QWEN: CodingRuntimePackage(
        runtime_id=RUNTIME_ID_QWEN,
        npm_package="@qwen-code/qwen-code",
        bin_name="qwen",
        label="Qwen Code",
        docs_url="https://qwen.ai/qwencode",
    ),
    RUNTIME_ID_DSH: CodingRuntimePackage(
        runtime_id=RUNTIME_ID_DSH,
        npm_package="@deepseek-ai/dsh",
        bin_name="dsh",
        label="DeepSeek Harness",
        docs_url="https://www.deepseek.com/en/harness/",
    ),
}


def npm_global_prefix() -> Path:
    return external_runtime_home_dir() / "npm-global"


def npm_global_bin_dir() -> Path:
    return npm_global_prefix() / "bin"


def _state_path() -> Path:
    return npm_global_prefix() / "install_state.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    prefix = npm_global_prefix()
    prefix.mkdir(parents=True, exist_ok=True)
    path = _state_path()
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _volume_binary_path(pkg: CodingRuntimePackage) -> Path:
    return npm_global_bin_dir() / pkg.bin_name


def volume_binary_installed(runtime_id: str) -> bool:
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return False
    path = _volume_binary_path(pkg)
    return path.is_file() and os.access(path, os.X_OK)


def resolve_runtime_binary(runtime_id: str) -> str | None:
    """Absolute path to the harness binary, preferring the volume npm prefix."""
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return None
    volume_bin = _volume_binary_path(pkg)
    if volume_bin.is_file() and os.access(volume_bin, os.X_OK):
        return str(volume_bin)
    # Env overrides (AGENT_QWEN_BIN / AGENT_DSH_BIN)
    from apps.backend.infrastructure.platform import config as cfg

    if pkg.runtime_id == RUNTIME_ID_QWEN:
        configured = str(getattr(cfg, "QWEN_BIN", "qwen") or "qwen").strip() or "qwen"
    elif pkg.runtime_id == RUNTIME_ID_DSH:
        configured = str(getattr(cfg, "DSH_BIN", "dsh") or "dsh").strip() or "dsh"
    else:
        configured = pkg.bin_name
    if os.path.isabs(configured) and os.path.isfile(configured):
        return configured
    which = shutil.which(configured)
    return which if which and os.path.isfile(which) else None


def _prepare_npm_dirs() -> tuple[Path, Path, Path] | dict[str, Any]:
    """Return (prefix, home, cache) or an error dict."""
    prefix = npm_global_prefix()
    home = external_runtime_home_dir() / "npm-home"
    cache = home / ".npm"
    try:
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "bin").mkdir(parents=True, exist_ok=True)
        (prefix / "lib").mkdir(parents=True, exist_ok=True)
        home.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"cannot create npm prefix: {exc}", "log": ""}
    return prefix, home, cache


def _npm_subprocess_env(*, home: Path, cache: Path, prefix: Path) -> dict[str, str]:
    # After entrypoint gosu to HOST_UID, HOME is /root or unset — pin cache on the volume.
    return {
        **os.environ,
        "HOME": str(home),
        "npm_config_cache": str(cache),
        "npm_config_prefix": str(prefix),
        "npm_config_update_notifier": "false",
        "npm_config_fund": "false",
        "npm_config_audit": "false",
        "npm_config_userconfig": str(home / ".npmrc"),
    }


def probe_binary_version(binary: str | None) -> str | None:
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if not text:
        return None
    m = _VERSION_RE.search(text)
    if m:
        return m.group(1)
    # First non-empty line as fallback
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:64]
    return None


def runtime_package_status(runtime_id: str) -> dict[str, Any]:
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return {"id": runtime_id, "error": "unknown_runtime"}
    binary = resolve_runtime_binary(pkg.runtime_id)
    version = probe_binary_version(binary)
    state = _load_state().get(pkg.runtime_id) or {}
    on_volume = volume_binary_installed(pkg.runtime_id)
    installed = bool(binary)
    source = "volume" if on_volume else ("image" if installed else None)
    return {
        "id": pkg.runtime_id,
        "label": pkg.label,
        "npm_package": pkg.npm_package,
        "docs_url": pkg.docs_url,
        "bin_name": pkg.bin_name,
        "installed": installed,
        "volume_installed": on_volume,
        "source": source,
        "binary_path": binary,
        "version": version or (str(state.get("version") or "").strip() or None),
        "requested_version": (str(state.get("requested") or "").strip() or None),
        "npm_prefix": str(npm_global_prefix()),
        "last_install_ok": state.get("ok"),
        "last_install_at": state.get("at"),
        "last_install_log_tail": state.get("log_tail"),
    }


def list_coding_runtime_package_status() -> list[dict[str, Any]]:
    return [runtime_package_status(rid) for rid in sorted(CODING_RUNTIME_PACKAGES)]


def list_npm_package_versions(
    runtime_id: str,
    *,
    limit: int = 40,
    timeout_sec: int = 45,
) -> dict[str, Any]:
    """Fetch installable versions + dist-tags from the npm registry for a coding runtime.

    Returns a select-friendly payload: ``latest`` first, then other tags, then newest
    published versions (capped). Never asks the operator to type a version string.
    """
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return {"ok": False, "error": f"unknown runtime {runtime_id!r}", "versions": [], "tags": {}}

    npm = shutil.which("npm")
    if not npm:
        return {"ok": False, "error": "npm not found on PATH", "versions": [], "tags": {}}

    prepared = _prepare_npm_dirs()
    if isinstance(prepared, dict):
        return {**prepared, "versions": [], "tags": {}}
    prefix, home, cache = prepared
    env = _npm_subprocess_env(home=home, cache=cache, prefix=prefix)

    def _npm_json(args: list[str]) -> Any | None:
        try:
            proc = subprocess.run(
                [npm, *args],
                capture_output=True,
                text=True,
                timeout=max(10, min(int(timeout_sec), 120)),
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        text = (proc.stdout or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    tags_raw = _npm_json(["view", pkg.npm_package, "dist-tags", "--json"])
    versions_raw = _npm_json(["view", pkg.npm_package, "versions", "--json"])

    tags: dict[str, str] = {}
    if isinstance(tags_raw, dict):
        for k, v in tags_raw.items():
            key = str(k).strip()
            val = str(v).strip()
            if key and val and re.fullmatch(r"[A-Za-z0-9._+\-]+", val):
                tags[key] = val

    versions: list[str] = []
    if isinstance(versions_raw, list):
        versions = [str(v).strip() for v in versions_raw if str(v).strip()]
    elif isinstance(versions_raw, str) and versions_raw.strip():
        versions = [versions_raw.strip()]

    # Newest first; keep only safe tokens
    versions = [v for v in reversed(versions) if re.fullmatch(r"[A-Za-z0-9._+\-]+", v)]
    cap = max(1, min(int(limit), 100))
    versions = versions[:cap]

    # Select options: dist-tag names (installable as @tag) then concrete versions
    options: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(value: str, label: str) -> None:
        if value in seen:
            return
        seen.add(value)
        options.append({"value": value, "label": label})

    if "latest" in tags:
        _add("latest", f"latest ({tags['latest']})")
    else:
        _add("latest", "latest")
    for tag, ver in sorted(tags.items()):
        if tag == "latest":
            continue
        _add(tag, f"{tag} ({ver})")
    for ver in versions:
        _add(ver, ver)

    if not options:
        return {
            "ok": False,
            "error": f"could not list versions for {pkg.npm_package}",
            "npm_package": pkg.npm_package,
            "versions": [],
            "tags": tags,
            "options": [],
        }

    return {
        "ok": True,
        "error": None,
        "npm_package": pkg.npm_package,
        "tags": tags,
        "versions": versions,
        "options": options,
        "default": "latest",
    }


def install_coding_runtime_package(
    runtime_id: str,
    *,
    version: str = "latest",
    timeout_sec: int = 600,
) -> dict[str, Any]:
    """Run ``npm install -g --prefix <volume> <pkg>@<version>``."""
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return {"ok": False, "error": f"unknown runtime {runtime_id!r}", "log": ""}

    ver = (version or "latest").strip() or "latest"
    # Reject shell metacharacters in version pins
    if not re.fullmatch(r"[A-Za-z0-9._+\-]+", ver):
        return {"ok": False, "error": f"invalid version {version!r}", "log": ""}

    npm = shutil.which("npm")
    if not npm:
        return {"ok": False, "error": "npm not found on PATH", "log": ""}

    prepared = _prepare_npm_dirs()
    if isinstance(prepared, dict):
        return prepared
    prefix, home, cache = prepared

    target = f"{pkg.npm_package}@{ver}"
    cmd = [npm, "install", "-g", "--prefix", str(prefix), target]
    logger.info("coding runtime install: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(60, min(int(timeout_sec), 3600)),
            check=False,
            env=_npm_subprocess_env(home=home, cache=cache, prefix=prefix),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"npm install timed out after {timeout_sec}s", "log": ""}
    except OSError as exc:
        return {"ok": False, "error": f"npm install failed to start: {exc}", "log": ""}

    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    log_tail = log[-4000:] if log else ""
    ok = proc.returncode == 0
    binary = resolve_runtime_binary(pkg.runtime_id) if ok else None
    probed = probe_binary_version(binary) if binary else None
    from datetime import datetime, timezone

    state = _load_state()
    state[pkg.runtime_id] = {
        "ok": ok,
        "at": datetime.now(timezone.utc).isoformat(),
        "requested": target,
        "version": probed or ver,
        "binary_path": binary,
        "log_tail": log_tail,
        "returncode": proc.returncode,
    }
    try:
        _save_state(state)
    except OSError:
        logger.warning("could not persist coding runtime install state", exc_info=True)

    if not ok:
        return {
            "ok": False,
            "error": f"npm install exited {proc.returncode}",
            "log": log_tail,
            "status": runtime_package_status(pkg.runtime_id),
        }
    return {
        "ok": True,
        "error": None,
        "log": log_tail,
        "status": runtime_package_status(pkg.runtime_id),
    }


def update_coding_runtime_package(runtime_id: str, *, timeout_sec: int = 600) -> dict[str, Any]:
    return install_coding_runtime_package(runtime_id, version="latest", timeout_sec=timeout_sec)


def uninstall_coding_runtime_package(runtime_id: str, *, timeout_sec: int = 300) -> dict[str, Any]:
    """Remove the package from the volume npm prefix (not image-baked /usr/local binaries)."""
    pkg = CODING_RUNTIME_PACKAGES.get(str(runtime_id or "").strip())
    if pkg is None:
        return {"ok": False, "error": f"unknown runtime {runtime_id!r}", "log": ""}

    if not volume_binary_installed(pkg.runtime_id):
        binary = resolve_runtime_binary(pkg.runtime_id)
        if binary:
            return {
                "ok": False,
                "error": (
                    f"{pkg.bin_name} is only available from the image/PATH ({binary}); "
                    "volume uninstall has nothing to remove. Rebuild the image to change that binary."
                ),
                "log": "",
                "status": runtime_package_status(pkg.runtime_id),
            }
        return {
            "ok": True,
            "error": None,
            "log": "nothing installed under the volume prefix",
            "status": runtime_package_status(pkg.runtime_id),
        }

    npm = shutil.which("npm")
    if not npm:
        return {"ok": False, "error": "npm not found on PATH", "log": ""}

    prepared = _prepare_npm_dirs()
    if isinstance(prepared, dict):
        return prepared
    prefix, home, cache = prepared

    cmd = [npm, "uninstall", "-g", "--prefix", str(prefix), pkg.npm_package]
    logger.info("coding runtime uninstall: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(30, min(int(timeout_sec), 1800)),
            check=False,
            env=_npm_subprocess_env(home=home, cache=cache, prefix=prefix),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"npm uninstall timed out after {timeout_sec}s", "log": ""}
    except OSError as exc:
        return {"ok": False, "error": f"npm uninstall failed to start: {exc}", "log": ""}

    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    log_tail = log[-4000:] if log else ""
    ok = proc.returncode == 0
    from datetime import datetime, timezone

    state = _load_state()
    if ok:
        state.pop(pkg.runtime_id, None)
    else:
        state[pkg.runtime_id] = {
            **(state.get(pkg.runtime_id) or {}),
            "ok": False,
            "at": datetime.now(timezone.utc).isoformat(),
            "log_tail": log_tail,
            "returncode": proc.returncode,
            "action": "uninstall",
        }
    try:
        _save_state(state)
    except OSError:
        logger.warning("could not persist coding runtime uninstall state", exc_info=True)

    if not ok:
        return {
            "ok": False,
            "error": f"npm uninstall exited {proc.returncode}",
            "log": log_tail,
            "status": runtime_package_status(pkg.runtime_id),
        }
    return {
        "ok": True,
        "error": None,
        "log": log_tail or "uninstalled from volume prefix",
        "status": runtime_package_status(pkg.runtime_id),
    }


__all__ = [
    "CODING_RUNTIME_PACKAGES",
    "RUNTIME_ID_DSH",
    "RUNTIME_ID_QWEN",
    "CodingRuntimePackage",
    "install_coding_runtime_package",
    "list_coding_runtime_package_status",
    "list_npm_package_versions",
    "npm_global_bin_dir",
    "npm_global_prefix",
    "resolve_runtime_binary",
    "runtime_package_status",
    "uninstall_coding_runtime_package",
    "update_coding_runtime_package",
    "volume_binary_installed",
]
