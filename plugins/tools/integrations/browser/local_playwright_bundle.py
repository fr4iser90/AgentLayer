"""
Validate structured browser-automation plans and export Playwright bundles for **local** execution.

Output directory: ``$AGENT_DATA_DIR/output/<user-id>/browser/local-playwright-bundles/<stamp>/``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
TOOL_ID = "local_playwright_bundle"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "browser"
TOOL_LABEL = "Local Playwright bundle"
TOOL_DESCRIPTION = (
    "Client-side browser automation: validate a structured JSON plan, or compile it into a "
    "downloadable Node + Playwright package (task.mjs, package.json, README, run.sh / run.ps1, "
    "manifest.json, optional assets) as a ZIP. Nothing runs in the server browser — the user runs "
    "`npm install`, `npx playwright install`, `npm start` on their machine. Use "
    "`validate_browser_automation_plan` first when the plan is complex; then "
    "`export_local_playwright_bundle` with the same `plan`."
)
# Per-function capabilities are set in AGENT_TOOL_META_BY_NAME (validate vs package).
TOOL_CAPABILITIES: tuple[str, ...] = ()
# Router phrases: co-located local_playwright_bundle.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
_PLAN_VERSION = 1
_MAX_STEPS = 120
_MAX_SELECTOR_LEN = 800
_MAX_VALUE_LEN = 32_000
_MAX_URL_LEN = 2048
_MAX_TITLE_LEN = 240
_MAX_ASSETS = 12
_MAX_ASSET_BYTES = 500_000

_ALLOWED_ACTIONS = frozenset({"goto", "click", "fill", "wait", "press", "upload"})
_ALLOWED_IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml"}
)

# Keys that must never appear in generated JS except via json.dumps
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _output_root() -> Path:
    from apps.backend.domain.shared.identity import get_identity
    from apps.backend.domain.agent_runtime.user_output import user_output_subdir
    from apps.backend.infrastructure.platform.config import config

    _, user_id = get_identity()
    return user_output_subdir(
        user_id,
        "browser",
        "local-playwright-bundles",
        base_dir=Path(config.DATA_DIR),
    )


def _parse_plan(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    plan = raw.get("plan")
    if isinstance(plan, str) and plan.strip():
        try:
            plan = json.loads(plan)
        except json.JSONDecodeError:
            return None
    if isinstance(plan, dict):
        return plan
    pj = raw.get("plan_json")
    if isinstance(pj, str) and pj.strip():
        try:
            o = json.loads(pj)
        except json.JSONDecodeError:
            return None
        return o if isinstance(o, dict) else None
    return None


def _localhost_host(host: str) -> bool:
    h = (host or "").lower().strip(".")
    return h in ("localhost", "127.0.0.1", "::1") or h.endswith(".localhost")


def _validate_url(url: str, errors: list[str], *, step_idx: int | None = None) -> None:
    prefix = f"steps[{step_idx}]." if step_idx is not None else ""
    if not isinstance(url, str) or not url.strip():
        errors.append(f"{prefix}url: non-empty string required")
        return
    u = url.strip()
    if len(u) > _MAX_URL_LEN:
        errors.append(f"{prefix}url: too long (max {_MAX_URL_LEN})")
        return
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        errors.append(f"{prefix}url: only http/https allowed, got {parsed.scheme!r}")
        return
    if parsed.scheme == "http" and not _localhost_host(parsed.hostname or ""):
        errors.append(f"{prefix}url: http is only allowed for localhost / 127.0.0.1 / ::1")
        return


def validate_browser_automation_plan_core(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate ``plan`` dict. Returns (ok, errors) where errors is non-empty if not ok.
    """
    errors: list[str] = []
    if not isinstance(plan, dict):
        return False, ["plan: object required"]

    ver = plan.get("version")
    if ver != _PLAN_VERSION:
        errors.append(f"version: must be integer {_PLAN_VERSION}, got {ver!r}")

    title = plan.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > _MAX_TITLE_LEN):
        errors.append(f"title: optional string, max {_MAX_TITLE_LEN} chars")

    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 1:
        errors.append("steps: non-empty array required")
    elif len(steps) > _MAX_STEPS:
        errors.append(f"steps: at most {_MAX_STEPS} steps allowed")

    prefixes = plan.get("allowed_host_prefixes")
    if prefixes is not None:
        if not isinstance(prefixes, list) or not all(isinstance(p, str) and p.strip() for p in prefixes):
            errors.append("allowed_host_prefixes: optional array of non-empty strings")
        else:
            for i, p in enumerate(prefixes):
                if len(p) > _MAX_URL_LEN:
                    errors.append(f"allowed_host_prefixes[{i}]: too long")

    asset_files = plan.get("asset_files")
    if asset_files is not None:
        if not isinstance(asset_files, list) or not all(isinstance(a, str) and a.strip() for a in asset_files):
            errors.append("asset_files: optional array of non-empty filename strings")
        elif len(asset_files) > _MAX_ASSETS:
            errors.append(f"asset_files: at most {_MAX_ASSETS} entries")

    headless = plan.get("headless")
    if headless is not None and not isinstance(headless, bool):
        errors.append("headless: optional boolean")

    if not isinstance(steps, list) or len(steps) < 1:
        return (len(errors) == 0), errors

    declared_assets: set[str] = set()
    if isinstance(asset_files, list):
        declared_assets = {str(a).strip() for a in asset_files if isinstance(a, str) and a.strip()}

    for i, step in enumerate(steps):
        sp = f"steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{sp}: object required")
            continue
        action = step.get("action")
        if action not in _ALLOWED_ACTIONS:
            errors.append(
                f"{sp}.action: must be one of {sorted(_ALLOWED_ACTIONS)}, got {action!r}"
            )
            continue
        if action == "goto":
            url = step.get("url")
            _validate_url(str(url) if url is not None else "", errors, step_idx=i)
            if isinstance(prefixes, list) and prefixes and isinstance(url, str) and url.strip():
                ok_pf = any(url.strip().startswith(p.strip()) for p in prefixes if isinstance(p, str))
                if not ok_pf:
                    errors.append(f"{sp}: url does not match any allowed_host_prefixes entry")
        elif action in ("click", "fill", "wait", "upload"):
            sel = step.get("selector")
            if not isinstance(sel, str) or not sel.strip():
                errors.append(f"{sp}.selector: non-empty string required")
            elif len(sel) > _MAX_SELECTOR_LEN:
                errors.append(f"{sp}.selector: too long (max {_MAX_SELECTOR_LEN})")
            if action == "fill":
                val = step.get("value")
                if not isinstance(val, str):
                    errors.append(f"{sp}.value: string required for fill")
                elif len(val) > _MAX_VALUE_LEN:
                    errors.append(f"{sp}.value: too long (max {_MAX_VALUE_LEN})")
            if action == "wait":
                to = step.get("timeout_ms")
                if to is not None:
                    if not isinstance(to, int) or isinstance(to, bool):
                        errors.append(f"{sp}.timeout_ms: integer or omit")
                    elif to < 100 or to > 600_000:
                        errors.append(f"{sp}.timeout_ms: must be between 100 and 600000")
            if action == "upload":
                asset = step.get("asset")
                if not isinstance(asset, str) or not asset.strip():
                    errors.append(f"{sp}.asset: non-empty string (filename under assets/) required")
                else:
                    an = asset.strip()
                    if an != Path(an).name or ".." in an or an.startswith(("/", "\\")):
                        errors.append(f"{sp}.asset: invalid filename")
                    elif declared_assets and an not in declared_assets:
                        errors.append(
                            f"{sp}.asset: {an!r} must appear in plan.asset_files (non-empty list)"
                        )
        elif action == "press":
            key = step.get("key", "Enter")
            if not isinstance(key, str) or not key.strip():
                errors.append(f"{sp}.key: non-empty string (default Enter)")
            elif not re.fullmatch(r"[A-Za-z0-9+\-_.\[\]]{1,64}", key.strip()):
                errors.append(f"{sp}.key: unsupported characters (use Playwright key names)")

    return (len(errors) == 0), errors


def _manifest_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    will: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        act = step.get("action")
        if act == "goto":
            will.append(f"Open {step.get('url', '')}")
        elif act == "click":
            will.append(f"Click element matching selector")
        elif act == "fill":
            will.append("Type text into an input")
        elif act == "wait":
            will.append("Wait for an element to appear")
        elif act == "upload":
            will.append("Upload a file from the assets folder")
        elif act == "press":
            will.append(f"Press key {step.get('key', 'Enter')!r}")
    wont = [
        "Does not run on the AgentLayer server",
        "Does not read passwords from the server",
        "Does not send network requests except via your Playwright script on your machine",
    ]
    return {
        "version": _PLAN_VERSION,
        "title": plan.get("title") if isinstance(plan.get("title"), str) else None,
        "summary": {"will": will, "wont": wont},
        "steps_count": len(steps),
        "asset_files": plan.get("asset_files") if isinstance(plan.get("asset_files"), list) else [],
        "headless": bool(plan.get("headless")) if isinstance(plan.get("headless"), bool) else False,
    }


def _emit_task_mjs(plan: dict[str, Any]) -> str:
    headless = "true" if plan.get("headless") is True else "false"
    lines: list[str] = [
        "import { chromium } from 'playwright';",
        "import { dirname, join } from 'path';",
        "import { fileURLToPath } from 'url';",
        "",
        "const __dirname = dirname(fileURLToPath(import.meta.url));",
        "",
        "async function main() {",
        f"  const browser = await chromium.launch({{ headless: {headless} }});",
        "  const context = await browser.newContext();",
        "  const page = await context.newPage();",
        "  try {",
    ]
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        act = step.get("action")
        if act == "goto":
            url = json.dumps(str(step.get("url", "")).strip())
            lines.append(f"    await page.goto({url});")
        elif act == "click":
            sel = json.dumps(str(step.get("selector", "")).strip())
            lines.append(f"    await page.click({sel});")
        elif act == "fill":
            sel = json.dumps(str(step.get("selector", "")).strip())
            val = json.dumps(str(step.get("value", "")))
            lines.append(f"    await page.fill({sel}, {val});")
        elif act == "wait":
            sel = json.dumps(str(step.get("selector", "")).strip())
            to = step.get("timeout_ms")
            if isinstance(to, int) and not isinstance(to, bool):
                lines.append(
                    f"    await page.waitForSelector({sel}, {{ timeout: {int(to)} }});"
                )
            else:
                lines.append(f"    await page.waitForSelector({sel});")
        elif act == "upload":
            sel = json.dumps(str(step.get("selector", "")).strip())
            asset = json.dumps(str(step.get("asset", "")).strip())
            lines.append(
                f"    await page.setInputFiles({sel}, "
                f"join(__dirname, 'assets', {asset}));"
            )
        elif act == "press":
            key = json.dumps(str(step.get("key", "Enter")).strip())
            lines.append(f"    await page.keyboard.press({key});")
    lines.extend(
        [
            "  } finally {",
            "    await context.close();",
            "    await browser.close();",
            "  }",
            "}",
            "",
            "main().catch((err) => {",
            "  console.error(err);",
            "  process.exit(1);",
            "});",
            "",
        ]
    )
    return "\n".join(lines)


def _write_bundle_files(bundle_dir: Path, plan: dict[str, Any], manifest: dict[str, Any]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = bundle_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    (bundle_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "agentlayer-local-browser-task",
                "version": "1.0.0",
                "private": True,
                "type": "module",
                "scripts": {"start": "node task.mjs"},
                "dependencies": {"playwright": "^1.49.0"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "task.mjs").write_text(_emit_task_mjs(plan), encoding="utf-8")
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    readme = """# Local browser task (Playwright)

Generated by AgentLayer. **Run only on your own machine** after reading `task.mjs` and `manifest.json`.

## Requirements

- Node.js 18+
- Network access to install npm packages and Playwright browsers

## Commands

```bash
npm install
npx playwright install
npm start
```

On Windows PowerShell:

```powershell
npm install; npx playwright install; npm start
```

Or use `run.sh` / `run.ps1` in this folder (installs deps then starts).

Scripts are plain text — review before running.
"""
    (bundle_dir / "README.md").write_text(readme, encoding="utf-8")
    (bundle_dir / "run.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\nnpm install\nnpx playwright install\nnpm start\n",
        encoding="utf-8",
    )
    (bundle_dir / "run.ps1").write_text(
        "Set-StrictMode -Version Latest\n"
        "$ErrorActionPreference = 'Stop'\n"
        "Set-Location $PSScriptRoot\n"
        "npm install\n"
        "npx playwright install\n"
        "npm start\n",
        encoding="utf-8",
    )
    try:
        (bundle_dir / "run.sh").chmod(0o755)
    except OSError:
        pass


def _validate_export_assets(arguments: dict[str, Any]) -> list[str]:
    """Validate optional ``assets`` before writing bundle (no side effects)."""
    errors: list[str] = []
    raw = arguments.get("assets")
    if not isinstance(raw, list) or not raw:
        return errors
    if len(raw) > _MAX_ASSETS:
        return [f"assets: at most {_MAX_ASSETS} files"]
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"assets[{i}]: object required")
            continue
        name = item.get("name")
        mime = item.get("media_type") or item.get("mime_type")
        b64 = item.get("data_base64")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"assets[{i}].name: string required")
            continue
        safe = Path(name.strip()).name
        if not safe or safe != name.strip() or ".." in name:
            errors.append(f"assets[{i}].name: invalid filename")
            continue
        if safe in seen:
            errors.append(f"assets[{i}].name: duplicate {safe!r}")
            continue
        seen.add(safe)
        if not isinstance(mime, str) or mime.strip() not in _ALLOWED_IMAGE_TYPES:
            errors.append(
                f"assets[{i}]: media_type must be one of {sorted(_ALLOWED_IMAGE_TYPES)}"
            )
            continue
        if not isinstance(b64, str) or not b64.strip():
            errors.append(f"assets[{i}].data_base64: non-empty string required")
            continue
        try:
            raw_bytes = base64.b64decode(b64.strip(), validate=True)
        except (ValueError, OSError) as e:
            errors.append(f"assets[{i}].data_base64: invalid base64 ({e})")
            continue
        if len(raw_bytes) > _MAX_ASSET_BYTES:
            errors.append(f"assets[{i}]: decoded file too large (max {_MAX_ASSET_BYTES} bytes)")
            continue
    return errors


def _materialize_plan_assets(bundle_dir: Path, arguments: dict[str, Any]) -> None:
    raw = arguments.get("assets")
    if not isinstance(raw, list) or not raw:
        return
    assets_dir = bundle_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        b64 = item.get("data_base64")
        if not isinstance(name, str) or not isinstance(b64, str):
            continue
        safe = Path(name.strip()).name
        raw_bytes = base64.b64decode(b64.strip(), validate=True)
        (assets_dir / safe).write_bytes(raw_bytes)


def _zip_bundle(bundle_dir: Path, zip_path: Path) -> str:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                arc = path.relative_to(bundle_dir).as_posix()
                zf.write(path, arcname=arc)
    h = hashlib.sha256()
    with zip_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_browser_automation_plan(arguments: dict[str, Any]) -> str:
    plan = _parse_plan(dict(arguments or {}))
    if plan is None:
        return json.dumps(
            {"ok": False, "errors": ["Missing or invalid `plan` (object) or `plan_json` string."]},
            ensure_ascii=False,
        )
    ok, errors = validate_browser_automation_plan_core(plan)
    return json.dumps({"ok": ok, "errors": errors, "manifest_preview": _manifest_from_plan(plan)}, ensure_ascii=False)


def export_local_playwright_bundle(arguments: dict[str, Any]) -> str:
    args = dict(arguments or {})
    plan = _parse_plan(args)
    if plan is None:
        return json.dumps(
            {
                "ok": False,
                "error": "Missing or invalid `plan` (object) or `plan_json` (stringified JSON).",
            },
            ensure_ascii=False,
        )
    ok, errors = validate_browser_automation_plan_core(plan)
    if not ok:
        return json.dumps({"ok": False, "errors": errors}, ensure_ascii=False)

    asset_errors = _validate_export_assets(args)
    if asset_errors:
        return json.dumps({"ok": False, "errors": asset_errors}, ensure_ascii=False)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    bundle_dir = _output_root() / f"{stamp}_{short}"
    manifest = _manifest_from_plan(plan)
    zip_path = bundle_dir.parent / f"{stamp}_{short}.zip"
    try:
        _write_bundle_files(bundle_dir, plan, manifest)
        _materialize_plan_assets(bundle_dir, args)
        digest = _zip_bundle(bundle_dir, zip_path)
    except Exception as e:
        logger.exception("export_local_playwright_bundle failed")
        shutil.rmtree(bundle_dir, ignore_errors=True)
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    rel_info: dict[str, str] = {}
    try:
        rel = bundle_dir.relative_to(_REPO_ROOT)
        rel_zip = zip_path.relative_to(_REPO_ROOT)
        rel_info = {"bundle_dir": rel.as_posix(), "zip": rel_zip.as_posix()}
    except ValueError:
        pass

    payload: dict[str, Any] = {
        "ok": True,
        "bundle_dir": str(bundle_dir),
        "zip_path": str(zip_path),
        "zip_sha256": digest,
        "manifest": manifest,
    }
    if rel_info:
        payload["paths_relative_to_repo_root"] = rel_info
    return json.dumps(payload, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "validate_browser_automation_plan": validate_browser_automation_plan,
    "export_local_playwright_bundle": export_local_playwright_bundle,
}

AGENT_TOOL_META_BY_NAME: dict[str, dict[str, Any]] = {
    "validate_browser_automation_plan": {"capabilities": ["automation.browser.validate"]},
    "export_local_playwright_bundle": {"capabilities": ["automation.browser.package"]},
}

_TOOLS_BODY: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "validate_browser_automation_plan",
            "TOOL_DESCRIPTION": (
                "Validate a structured browser automation plan (JSON only). Does not write files. "
                "Returns ok/errors and a manifest_preview. Plan fields: version (1), optional title, "
                "optional allowed_host_prefixes (every goto URL must start with one), optional headless (bool), "
                "optional asset_files (filenames for upload steps), steps[] with action in "
                "goto|click|fill|wait|press|upload."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Structured plan object (see tool description).",
                    },
                    "plan_json": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alternative: entire plan as a JSON string (if the model emits a string).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_local_playwright_bundle",
            "TOOL_DESCRIPTION": (
                "After a valid plan: write a Playwright Node package (task.mjs, package.json, README, "
                "run.sh, run.ps1, manifest.json), optional image assets, zip the folder, return paths and "
                "zip_sha256. User runs the bundle locally — not on the server."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Same structured plan as validate_browser_automation_plan.",
                    },
                    "plan_json": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alternative: stringified JSON plan.",
                    },
                    "assets": {
                        "type": "array",
                        "TOOL_DESCRIPTION": (
                            "Optional images to place under assets/. Each: name (filename), "
                            "media_type (image/png, …), data_base64 (no data: prefix)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "media_type": {"type": "string"},
                                "data_base64": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
]

TOOLS: list[dict[str, Any]] = _TOOLS_BODY
