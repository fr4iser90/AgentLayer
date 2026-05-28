"""Frontend i18n and route coverage tests (runs Node scripts in apps/frontend)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "apps" / "frontend"


def _node() -> str:
    return shutil.which("node") or "node"


def test_frontend_i18n_locale_parity_and_ui_scan() -> None:
    """en/de JSON parity + all app routes + no hardcoded UI / t-shadowing in scanned dirs."""
    node = _node()
    script = FRONTEND / "scripts" / "test-frontend-i18n.mjs"
    assert script.is_file(), f"missing {script}"
    proc = subprocess.run(
        [node, str(script)],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stdout + proc.stderr
        raise AssertionError(
            f"frontend i18n tests failed (exit {proc.returncode}):\n{msg}"
        )


def _app_route_paths_from_tsx(content: str) -> set[str]:
    """Resolve nested React Router paths under basename /app."""
    import re

    skip_segment = {
        "*",
        "experimental",
        "coding-agent",
        "discord",
        "telegram",
        "workflows",
    }
    paths: set[str] = set()
    stack: list[str] = []

    def full_path() -> str:
        if not stack:
            return "/app/"
        return "/app/" + "/".join(stack)

    for line in content.splitlines():
        if "</Route>" in line:
            if stack:
                stack.pop()
            continue
        if "<Route" not in line:
            continue

        self_closing = line.strip().endswith("/>")
        pushed = False

        if re.search(
            r'element=\{<(Navigate|SettingsLayout|AdminLayout|InterfacesLayout|RequireAdmin|RequireSession|AppLayout)',
            line,
        ):
            path_m = re.search(r'path="([^"]+)"', line)
            if path_m:
                seg = path_m.group(1)
                if seg not in skip_segment and seg != "/":
                    stack.append(seg.strip("/"))
                    pushed = True
            if self_closing and pushed:
                stack.pop()
            continue

        path_m = re.search(r'path="([^"]+)"', line)
        if path_m:
            seg = path_m.group(1)
            if seg in skip_segment:
                continue
            if seg == "/":
                paths.add("/app/")
                continue
            stack.append(seg.strip("/"))
            pushed = True

        if re.search(r"<Route\s+index\b", line) or re.search(
            r"element=\{<[A-Z][A-Za-z]+(Page|Settings|Tools|Users|Schedules|ScheduledJobs|AgentTraces)",
            line,
        ):
            paths.add(full_path())

        if self_closing and pushed:
            stack.pop()

    return paths


def test_frontend_route_manifest_matches_app_routes() -> None:
    """Every page route in App.tsx (except redirects) should be listed in routes-manifest."""
    import re

    app_tsx = FRONTEND / "src" / "App.tsx"
    manifest = (FRONTEND / "scripts" / "routes-manifest.mjs").read_text(encoding="utf-8")
    content = app_tsx.read_text(encoding="utf-8")

    paths_in_app = _app_route_paths_from_tsx(content)
    listed = set(re.findall(r'path: "(/app[^"]*)"', manifest))

    missing = sorted(paths_in_app - listed)
    extra = sorted(listed - paths_in_app)
    assert not missing, f"routes-manifest.mjs missing paths from App.tsx: {missing}"
    assert not extra, f"routes-manifest.mjs has unknown paths vs App.tsx: {extra}"

    main_py = (REPO_ROOT / "apps/backend/api/main.py").read_text(encoding="utf-8")
    spa_routes = set(re.findall(r'@app\.get\("(/app[^"]+)"\)', main_py))
    # /app/ is served via agent_ui_spa_root, not the multi-decorator shell
    missing_spa = sorted(paths_in_app - spa_routes - {"/app/"})
    assert not missing_spa, (
        "main.py agent_ui_spa_shell missing hard-refresh routes: "
        f"{missing_spa}"
    )
