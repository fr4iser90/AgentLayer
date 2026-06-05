#!/usr/bin/env python3
"""
Standalone bootstrap / load perf probe — run anytime against a live Agent Layer.

  python3 scripts/diag/bootstrap_perf.py
  python3 scripts/diag/bootstrap_perf.py --base http://127.0.0.1:8088 --json

Not part of the app; no product metrics endpoints. Prints timings to stdout.
Exit 1 if any check exceeds budget (override with env AGENT_PERF_*_MAX_MS).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]


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


def env_ms(name: str, default: int) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return float(default)
    return float(raw)


def elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


@dataclass
class Sample:
    name: str
    ms: float
    ok: bool
    detail: str = ""


@dataclass
class Report:
    base: str
    samples: list[Sample]
    auth_chain: dict[str, Any]
    concurrent: dict[str, Any]
    browser: dict[str, Any] | None
    failures: list[str]
    diagnosis: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "samples": [asdict(s) for s in self.samples],
            "auth_chain": self.auth_chain,
            "concurrent": self.concurrent,
            "browser": self.browser,
            "failures": self.failures,
            "diagnosis": self.diagnosis,
        }


def timed_get(client: httpx.Client, path: str, *, name: str, ok_status: set[int]) -> Sample:
    t0 = time.perf_counter()
    try:
        r = client.get(path)
        ms = elapsed_ms(t0)
        ok = r.status_code in ok_status
        detail = f"http={r.status_code}"
        if ok and r.headers.get("content-type", "").startswith("application/json"):
            try:
                body = r.json()
                if isinstance(body, dict):
                    detail += f" keys={list(body.keys())[:6]}"
            except Exception:
                pass
        return Sample(name=name, ms=ms, ok=ok, detail=detail)
    except Exception as exc:
        return Sample(name=name, ms=elapsed_ms(t0), ok=False, detail=str(exc)[:200])


def timed_post(client: httpx.Client, path: str, *, name: str, ok_status: set[int], body: dict | None = None) -> Sample:
    t0 = time.perf_counter()
    try:
        r = client.post(path, json=body or {})
        ms = elapsed_ms(t0)
        ok = r.status_code in ok_status
        return Sample(name=name, ms=ms, ok=ok, detail=f"http={r.status_code}")
    except Exception as exc:
        return Sample(name=name, ms=elapsed_ms(t0), ok=False, detail=str(exc)[:200])


def concurrent_probe(base: str, path: str, n: int, *, auth: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": auth} if auth else None

    def one(_: int) -> float:
        t0 = time.perf_counter()
        with httpx.Client(base_url=base, timeout=30.0, headers=headers) as c:
            r = c.get(path)
            r.raise_for_status()
        return elapsed_ms(t0)

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        latencies = list(pool.map(one, range(n)))
    total = elapsed_ms(t0)
    latencies.sort()
    p95_i = max(0, int(0.95 * len(latencies)) - 1)
    return {
        "path": path,
        "n": n,
        "total_ms": total,
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "p95_ms": latencies[p95_i],
        "mean_ms": round(sum(latencies) / len(latencies), 2),
    }


def login_token(base: str, email: str, password: str) -> str:
    with httpx.Client(base_url=base, timeout=30.0) as c:
        r = c.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        tok = str(r.json().get("access_token") or "")
    if not tok:
        raise RuntimeError("login missing access_token")
    return tok


def creds() -> tuple[str, str] | None:
    email = (
        os.environ.get("AGENT_E2E_EMAIL")
        or os.environ.get("AGENT_TEST_EMAIL")
        or os.environ.get("AGENT_INITIAL_ADMIN_EMAIL")
        or ""
    ).strip()
    password = (
        os.environ.get("AGENT_E2E_PASSWORD")
        or os.environ.get("AGENT_TEST_PASSWORD")
        or os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD")
        or ""
    ).strip()
    if email and password:
        return email, password
    return None


def measure_auth_chain(client: httpx.Client) -> dict[str, Any]:
    """Mimics AuthContext bootstrap: setup-status and refresh in parallel."""
    t_chain = time.perf_counter()
    t0 = time.perf_counter()
    r1 = client.get("/auth/setup-status")
    cold_setup_ms = elapsed_ms(t0)
    t0 = time.perf_counter()
    r2 = client.get("/auth/setup-status")
    warm_setup_ms = elapsed_ms(t0)
    t0 = time.perf_counter()
    r3 = client.post("/auth/refresh", json={})
    refresh_ms = elapsed_ms(t0)
    total_ms = elapsed_ms(t_chain)
    return {
        "cold_setup_ms": cold_setup_ms,
        "warm_setup_ms": warm_setup_ms,
        "refresh_ms": refresh_ms,
        "chain_total_ms": total_ms,
        "setup_http": r1.status_code,
        "refresh_http": r3.status_code,
        "note": "chain_total ≈ time on 'Wird geladen…' before redirect (one SPA load)",
    }


def build_diagnosis(report: "Report") -> list[str]:
    lines: list[str] = []
    chain = report.auth_chain
    cold = float(chain.get("cold_setup_ms") or 0)
    warm = float(chain.get("warm_setup_ms") or 0)
    refresh = float(chain.get("refresh_ms") or 0)
    total = float(chain.get("chain_total_ms") or 0)

    if cold > 50 and warm < 10:
        lines.append(
            f"First /auth/setup-status is slow ({cold}ms) then warm ({warm}ms) — "
            "normal after idle/DB cold start; not caused by projects dashboard."
        )
    if refresh > 2000:
        lines.append(
            f"POST /auth/refresh took {refresh}ms — likely container cold start or DB pool; "
            "can block 'Wird geladen…' for seconds (timeout max 15s in frontend)."
        )
    elif refresh < 100 and total < 500:
        lines.append(
            f"Auth chain is fast ({total}ms total). If UI still feels slow, cause is usually "
            "double page load: protected route → window.location.replace('/app/login') runs bootstrap twice."
        )

    for s in report.samples:
        if s.name == "POST /auth/login" and s.ms > 300:
            lines.append(
                f"Login takes ~{s.ms}ms (password hash + DB) — normal, unrelated to dashboard kind."
            )

    if not lines:
        lines.append("All probes within normal range on this run.")
    return lines


def run_report(base: str, *, concurrent_n: int, with_auth: bool) -> Report:
    samples: list[Sample] = []
    failures: list[str] = []

    max_health = env_ms("AGENT_PERF_HEALTH_MAX_MS", 5000)
    max_setup = env_ms("AGENT_PERF_SETUP_MAX_MS", 5000)
    max_refresh = env_ms("AGENT_PERF_REFRESH_MAX_MS", 5000)
    max_app = env_ms("AGENT_PERF_APP_SHELL_MAX_MS", 20000)
    max_p95 = env_ms("AGENT_PERF_HEALTH_P95_MAX_MS", 5000)
    max_dash_p95 = env_ms("AGENT_PERF_DASHBOARDS_P95_MAX_MS", 15000)
    max_chain = env_ms("AGENT_PERF_AUTH_CHAIN_MAX_MS", 15000)

    auth_chain: dict[str, Any] = {}
    with httpx.Client(base_url=base, timeout=30.0, follow_redirects=True) as client:
        auth_chain = measure_auth_chain(client)
        samples.append(timed_get(client, "/health", name="GET /health", ok_status={200}))
        samples.append(
            timed_get(client, "/auth/setup-status", name="GET /auth/setup-status (single)", ok_status={200})
        )
        samples.append(
            timed_post(
                client,
                "/auth/refresh",
                name="POST /auth/refresh (no cookie)",
                ok_status={400, 401},
            )
        )
        t0 = time.perf_counter()
        try:
            r = client.get("/app/")
            ms = elapsed_ms(t0)
            ok = r.status_code == 200 and len(r.text) > 100
            samples.append(
                Sample(
                    name="GET /app/ (HTML shell)",
                    ms=ms,
                    ok=ok,
                    detail=f"http={r.status_code} bytes={len(r.text)}",
                )
            )
        except Exception as exc:
            samples.append(
                Sample(name="GET /app/ (HTML shell)", ms=elapsed_ms(t0), ok=False, detail=str(exc)[:200])
            )

        if with_auth:
            c = creds()
            if c:
                email, password = c
                t0 = time.perf_counter()
                try:
                    tok = login_token(base, email, password)
                    samples.append(
                        Sample(
                            name="POST /auth/login",
                            ms=elapsed_ms(t0),
                            ok=True,
                            detail=f"token_len={len(tok)}",
                        )
                    )
                    t0 = time.perf_counter()
                    r = client.get("/v1/dashboards", headers={"Authorization": f"Bearer {tok}"})
                    samples.append(
                        Sample(
                            name="GET /v1/dashboards (auth)",
                            ms=elapsed_ms(t0),
                            ok=r.status_code == 200,
                            detail=f"http={r.status_code}",
                        )
                    )
                except Exception as exc:
                    samples.append(
                        Sample(name="POST /auth/login", ms=elapsed_ms(t0), ok=False, detail=str(exc)[:200])
                    )
            else:
                samples.append(
                    Sample(
                        name="auth probes",
                        ms=0,
                        ok=True,
                        detail="skipped (no AGENT_INITIAL_ADMIN_* in .env)",
                    )
                )

    concurrent: dict[str, Any] = {}
    try:
        concurrent["health"] = concurrent_probe(base, "/health", concurrent_n)
    except Exception as exc:
        concurrent["health"] = {"error": str(exc)[:200]}
    if with_auth and creds():
        try:
            tok = login_token(base, creds()[0], creds()[1])  # type: ignore[index]
            concurrent["dashboards"] = concurrent_probe(
                base, "/v1/dashboards", min(concurrent_n, 10), auth=f"Bearer {tok}"
            )
        except Exception as exc:
            concurrent["dashboards"] = {"error": str(exc)[:200]}

    for s in samples:
        if not s.ok:
            failures.append(f"{s.name}: {s.detail}")
        elif s.name == "GET /health" and s.ms > max_health:
            failures.append(f"{s.name}: {s.ms}ms > budget {max_health}ms")
        elif s.name == "GET /auth/setup-status" and s.ms > max_setup:
            failures.append(f"{s.name}: {s.ms}ms > budget {max_setup}ms")
        elif s.name.startswith("POST /auth/refresh") and s.ms > max_refresh:
            failures.append(f"{s.name}: {s.ms}ms > budget {max_refresh}ms")
        elif s.name.startswith("GET /app/") and s.ms > max_app:
            failures.append(f"{s.name}: {s.ms}ms > budget {max_app}ms")

    h = concurrent.get("health")
    if isinstance(h, dict) and "p95_ms" in h and h["p95_ms"] > max_p95:
        failures.append(f"concurrent /health p95: {h['p95_ms']}ms > {max_p95}ms")
    d = concurrent.get("dashboards")
    if isinstance(d, dict) and "p95_ms" in d and d["p95_ms"] > max_dash_p95:
        failures.append(f"concurrent /v1/dashboards p95: {d['p95_ms']}ms > {max_dash_p95}ms")
    if auth_chain.get("chain_total_ms", 0) > max_chain:
        failures.append(
            f"auth chain: {auth_chain.get('chain_total_ms')}ms > budget {max_chain}ms"
        )

    report = Report(
        base=base,
        samples=samples,
        auth_chain=auth_chain,
        concurrent=concurrent,
        browser=None,
        failures=failures,
        diagnosis=[],
    )
    report.diagnosis = build_diagnosis(report)
    return report


def print_human(report: Report) -> None:
    print(f"\n=== Agent Layer bootstrap perf ===\nbase: {report.base}\n")
    print(f"{'check':<36} {'ms':>8}  {'ok':>4}  detail")
    print("-" * 72)
    for s in report.samples:
        ok = "yes" if s.ok else "NO"
        print(f"{s.name:<36} {s.ms:>8.2f}  {ok:>4}  {s.detail}")
    ac = report.auth_chain
    if ac:
        print("\n--- auth chain (Wird geladen… block) ---")
        print(
            f"  cold setup-status: {ac.get('cold_setup_ms')}ms  "
            f"warm: {ac.get('warm_setup_ms')}ms  "
            f"refresh: {ac.get('refresh_ms')}ms  "
            f"TOTAL: {ac.get('chain_total_ms')}ms"
        )
    print("\n--- concurrent ---")
    for key, val in report.concurrent.items():
        if isinstance(val, dict) and "error" in val:
            print(f"  {key}: ERROR {val['error']}")
        elif isinstance(val, dict):
            print(
                f"  {key}: n={val.get('n')} total={val.get('total_ms')}ms "
                f"min={val.get('min_ms')} p95={val.get('p95_ms')} max={val.get('max_ms')}ms"
            )
        else:
            print(f"  {key}: {val}")
    if report.diagnosis:
        print("\n--- why slow sometimes? ---")
        for line in report.diagnosis:
            print(f"  • {line}")
    if report.failures:
        print("\n--- FAIL ---")
        for f in report.failures:
            print(f"  • {f}")
    else:
        print("\nOK — all checks within budget")


def main() -> int:
    load_dotenv(REPO / ".env")
    load_dotenv(REPO / ".env.e2e")

    p = argparse.ArgumentParser(description="Agent Layer bootstrap/load perf probe")
    p.add_argument("--base", help="Base URL (default from AGENT_E2E_BASE_URL or :8088)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--no-auth", action="store_true", help="Skip login + /v1/dashboards probes")
    p.add_argument(
        "--concurrent",
        type=int,
        default=int(os.environ.get("AGENT_PERF_CONCURRENT", "20")),
        help="Parallel requests for multi-access probe (default 20)",
    )
    args = p.parse_args()

    base = base_url(args.base)
    try:
        with httpx.Client(base_url=base, timeout=5.0) as c:
            c.get("/health").raise_for_status()
    except Exception as exc:
        print(f"[perf] server not reachable at {base}: {exc}", file=sys.stderr)
        return 2

    report = run_report(base, concurrent_n=max(1, args.concurrent), with_auth=not args.no_auth)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human(report)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
