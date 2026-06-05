#!/usr/bin/env python3
"""
Browser E2E runtime perf — real page load metrics (Playwright), not auth-only HTTP probes.

  python3 scripts/diag/runtime_e2e_perf.py
  python3 scripts/diag/runtime_e2e_perf.py --base http://127.0.0.1:8088 --json

Measures:
  - "Wird geladen…" duration on /app/dashboard without session → redirect to login
  - Login + key routes (/app/, /app/dashboard, /app/chat) until UI ready
  - Slow API calls captured in the browser
  - 2 parallel dashboard loads (multi-access smoke)

Standalone diagnostic — NOT product instrumentation. No .sh wrappers.
Uses Docker Playwright image if local node/playwright is unavailable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "apps" / "frontend"
MJS = FRONTEND / "scripts" / "runtime_e2e_perf.mjs"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.49.1-noble"
JSON_MARKER = "__RUNTIME_E2E_JSON__"


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def base_url(explicit: str | None) -> str:
    if explicit:
        return explicit.rstrip("/")
    env = (os.environ.get("AGENT_E2E_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    port = (os.environ.get("AGENT_HTTP_PORT") or "8088").strip()
    return f"http://127.0.0.1:{port}"


def elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def parse_browser_json(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        if line.startswith(JSON_MARKER):
            return json.loads(line[len(JSON_MARKER) :])
    raise RuntimeError(f"browser probe missing {JSON_MARKER} line in output:\n{stdout[-2000:]}")


def run_browser_probe(base: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["AGENT_E2E_BASE_URL"] = base
    env["RUNTIME_E2E_JSON"] = "1"

    if shutil.which("node"):
        try:
            proc = subprocess.run(
                ["node", str(MJS)],
                cwd=str(FRONTEND),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if proc.returncode == 0:
                return parse_browser_json(proc.stdout)
        except Exception:
            pass

    if not shutil.which("docker"):
        raise RuntimeError(
            "Playwright probe needs node+playwright or docker. "
            "Install: npm install playwright@1.49.1 --prefix apps/frontend --no-save "
            "&& npx playwright install chromium"
        )

    env_file = REPO / ".env"
    docker_cmd: list[str] = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{REPO}:/work",
        "-w",
        "/work/apps/frontend",
        "-e",
        f"AGENT_E2E_BASE_URL={base}",
        "-e",
        "RUNTIME_E2E_JSON=1",
    ]
    if env_file.is_file():
        docker_cmd.extend(["--env-file", str(env_file)])
    docker_cmd.extend(
        [
            PLAYWRIGHT_IMAGE,
            "bash",
            "-lc",
            (
                "npm install playwright@1.49.1 --no-save "
                "&& node scripts/runtime_e2e_perf.mjs"
            ),
        ]
    )

    proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker playwright probe failed (exit {proc.returncode}):\n{proc.stderr[-1500:]}"
        )
    return parse_browser_json(proc.stdout)


def http_multi_access(base: str, n: int = 10) -> dict[str, Any]:
    def one(_: int) -> float:
        t0 = time.perf_counter()
        with httpx.Client(base_url=base, timeout=30.0) as c:
            c.get("/health").raise_for_status()
        return elapsed_ms(t0)

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        latencies = list(pool.map(one, range(n)))
    latencies.sort()
    p95_i = max(0, int(0.95 * len(latencies)) - 1)
    return {
        "path": "/health",
        "n": n,
        "total_ms": elapsed_ms(t0),
        "p95_ms": latencies[p95_i],
        "max_ms": max(latencies),
    }


def build_diagnosis(browser: dict[str, Any], http: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    scenarios = browser.get("scenarios") or []

    unauth = next((s for s in scenarios if "no session" in str(s.get("route", ""))), None)
    setup = next(
        (
            a
            for sc in scenarios
            for a in sc.get("api_calls") or []
            if "/auth/setup-status" in a.get("path", "") and a.get("ms", 0) > 500
        ),
        None,
    )
    if setup:
        lines.append(
            f"Slow GET /auth/setup-status (~{setup.get('ms')}ms in browser) — "
            "DB/instance check cold start; blocks every new page load. Not projects dashboard."
        )

    if unauth:
        spin = float(unauth.get("spinner_until_redirect_ms") or 0)
        refresh = next(
            (a for a in unauth.get("api_calls") or [] if "/auth/refresh" in a.get("path", "")),
            None,
        )
        refresh_ms = float(refresh.get("ms") or 0) if refresh else 0
        if spin > 2000 or refresh_ms > 2000:
            lines.append(
                f"Browser: 'Wird geladen…' on /app/dashboard took {spin}ms — "
                f"POST /auth/refresh ~{refresh_ms}ms. "
                "Typical after container cold start (not projects dashboard)."
            )
        elif spin > 500:
            lines.append(
                f"Browser spinner {spin}ms before login redirect — check Network tab for slow /auth/refresh."
            )
        else:
            lines.append(
                f"Unauthenticated /app/dashboard: spinner {spin}ms then redirect "
                f"{unauth.get('final_url', '?')} — auth bootstrap is fast on this run."
            )

    dash = next((s for s in scenarios if s.get("route") == "/app/dashboard"), None)
    if dash:
        ready = float(dash.get("ready_ms") or 0)
        login = float(dash.get("login_ms") or 0)
        if ready < 500 and login > 2000:
            lines.append(
                f"/app/dashboard UI ready in {ready}ms after login — "
                f"dashboard itself is fast; login path took {login}ms (setup-status + password hash)."
            )
        elif ready > 3000:
            lines.append(
                f"Dashboard UI ready in {ready}ms — check slow_resources / Network tab."
            )

    conc = browser.get("concurrent")
    if isinstance(conc, dict) and conc.get("max_ms"):
        mx = float(conc["max_ms"])
        if mx > 5000:
            lines.append(f"2 parallel dashboard loads: max {mx}ms — server or DB under parallel load.")
        else:
            lines.append(f"Multi-access (2× dashboard): {conc.get('latencies_ms')} — OK.")

    if http.get("p95_ms", 0) > 500:
        lines.append(f"HTTP {http.get('n')}× /health p95 {http['p95_ms']}ms — backend load.")

    if not lines:
        lines.append("Runtime E2E within normal range on this run.")
    return lines


@dataclass
class Report:
    base: str
    browser: dict[str, Any]
    http_concurrent: dict[str, Any]
    diagnosis: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "browser": self.browser,
            "http_concurrent": self.http_concurrent,
            "diagnosis": self.diagnosis,
            "failures": self.failures,
        }


def print_human(report: Report) -> None:
    print(f"\n=== Agent Layer RUNTIME E2E perf (browser) ===\nbase: {report.base}\n")
    for sc in report.browser.get("scenarios") or []:
        route = sc.get("route", "?")
        print(f"--- {route} ---")
        for key in (
            "dom_ms",
            "spinner_until_redirect_ms",
            "final_url",
            "login_ms",
            "ready_ms",
            "total_ms",
        ):
            if key in sc and sc[key] is not None:
                print(f"  {key}: {sc[key]}")
        api = sc.get("api_calls") or []
        if api:
            print("  api_calls (slowest first):")
            for row in api[:6]:
                print(
                    f"    {row.get('method', 'GET'):<4} {row.get('path', '?')}: "
                    f"{row.get('ms')}ms http={row.get('status')}"
                )
        slow = sc.get("slow_resources") or []
        if slow:
            print("  slow_resources:")
            for row in slow[:5]:
                url = str(row.get("url", "")).replace(report.base, "")
                print(f"    {url}: {row.get('ms')}ms")

    conc = report.browser.get("concurrent")
    if conc:
        print("\n--- multi-access (2× dashboard, separate sessions) ---")
        print(f"  latencies_ms: {conc.get('latencies_ms')}  max: {conc.get('max_ms')}ms")

    h = report.http_concurrent
    print(f"\n--- HTTP concurrent {h.get('n')}× {h.get('path')} ---")
    print(f"  p95={h.get('p95_ms')}ms  max={h.get('max_ms')}ms  total={h.get('total_ms')}ms")

    if report.browser.get("errors"):
        print("\n--- warnings ---")
        for err in report.browser["errors"]:
            print(f"  • {err}")

    print("\n--- why slow sometimes? ---")
    for line in report.diagnosis:
        print(f"  • {line}")

    if report.failures:
        print("\n--- FAIL ---")
        for f in report.failures:
            print(f"  • {f}")
    else:
        print("\nOK — runtime probes completed")


def main() -> int:
    load_dotenv(REPO / ".env")
    load_dotenv(REPO / ".env.e2e")

    p = argparse.ArgumentParser(description="Agent Layer runtime E2E perf (Playwright)")
    p.add_argument("--base", help="Base URL (default :8088)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument(
        "--http-only",
        action="store_true",
        help="Skip browser (HTTP multi-access only)",
    )
    args = p.parse_args()

    base = base_url(args.base)
    try:
        with httpx.Client(base_url=base, timeout=5.0) as c:
            c.get("/health").raise_for_status()
    except Exception as exc:
        print(f"[runtime-e2e] server not reachable at {base}: {exc}", file=sys.stderr)
        return 2

    http_conc = http_multi_access(base)
    browser: dict[str, Any] = {"scenarios": [], "errors": []}
    failures: list[str] = []

    if not args.http_only:
        try:
            browser = run_browser_probe(base)
        except Exception as exc:
            failures.append(str(exc)[:300])
            browser["errors"] = [str(exc)[:300]]

    report = Report(
        base=base,
        browser=browser,
        http_concurrent=http_conc,
        diagnosis=build_diagnosis(browser, http_conc),
        failures=failures,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human(report)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
