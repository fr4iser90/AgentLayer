"""Frontend i18n and route coverage tests (runs Node scripts in apps/frontend)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "apps" / "frontend"


def _node() -> str:
    return shutil.which("node") or "node"


def test_frontend_i18n_locale_parity_and_ui_scan() -> None:
    """en/de JSON parity + all app routes + no hardcoded UI / t-shadowing in scanned dirs."""
    import pytest

    node = _node()
    if not shutil.which("node"):
        pytest.skip("node not in PATH (frontend i18n script needs Node)")
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

    route_open = False
    route_pushed_seg = False

    for line in content.splitlines():
        if "</Route>" in line:
            if stack:
                stack.pop()
            route_open = False
            route_pushed_seg = False
            continue
        if "<Route" not in line:
            if route_open:
                path_m = re.search(r'path="([^"]+)"', line)
                if path_m:
                    seg = path_m.group(1)
                    if seg not in skip_segment and seg != "/":
                        stack.append(seg.strip("/"))
                        route_pushed_seg = True
                if re.search(
                    r"<\w+(?:Page|Settings|Tools|Users|Schedules|ScheduledJobs|AgentTraces|Agents|Benchmarks|Dashboard)\s*/?>",
                    line,
                ):
                    paths.add(full_path())
                if line.strip().endswith("/>") and route_pushed_seg:
                    stack.pop()
                    route_open = False
                    route_pushed_seg = False
            continue

        if not line.strip().endswith("/>"):
            route_open = True
            route_pushed_seg = False

        self_closing = line.strip().endswith("/>")
        pushed = False

        if re.search(
            r'element=\{<(Navigate|SettingsLayout|AdminLayout|InterfacesLayout|RequireAdmin|RequireSession|AppLayout|RequireOrgAdmin|OrgAdminLayout)',
            line,
        ):
            path_m = re.search(r'path="([^"]+)"', line)
            if path_m:
                seg = path_m.group(1)
                if seg not in skip_segment and seg != "/":
                    stack.append(seg.strip("/"))
                    pushed = True
                    route_pushed_seg = True
            if self_closing and pushed:
                stack.pop()
                route_open = False
                route_pushed_seg = False
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
            route_pushed_seg = True

        if re.search(r"<Route\s+index\b", line) or re.search(
            r"element=\{<[A-Z][A-Za-z]+(?:Page|Settings|Tools|Users|Schedules|ScheduledJobs|AgentTraces|Agents|Benchmarks|Dashboard)",
            line,
        ) or re.search(
            r"<\w+(?:Page|Settings|Tools|Users|Schedules|ScheduledJobs|AgentTraces|Agents|Benchmarks|Dashboard)\s*/?>",
            line,
        ):
            paths.add(full_path())

        if self_closing and pushed:
            stack.pop()
            route_open = False
            route_pushed_seg = False
        elif self_closing and route_open and route_pushed_seg and "<Route" not in line:
            stack.pop()
            route_open = False
            route_pushed_seg = False

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

    web_api_py = (REPO_ROOT / "apps/backend/api/platform/controllers/web_api.py").read_text(encoding="utf-8")
    spa_routes = set(re.findall(r'@app\.get\("(/app[^"]+)"\)', web_api_py))

    def _dyn_key(path: str) -> str:
        # React ``:slug`` and FastAPI ``{slug}`` / ``{rest:path}`` are equivalent for coverage.
        return re.sub(r"/(:[^/]+|\{[^}]+\})", "/*", path)

    spa_keys = {_dyn_key(p) for p in spa_routes}
    # /app/ is served via agent_ui_spa_root, not the multi-decorator shell
    missing_spa = sorted(
        p for p in paths_in_app if p != "/app/" and _dyn_key(p) not in spa_keys
    )
    assert not missing_spa, (
        "web_api.py agent_ui_spa_shell missing hard-refresh routes: "
        f"{missing_spa}"
    )
