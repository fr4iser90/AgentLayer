"""
Prove POST /auth/refresh latency scales with refresh_tokens row count.

Mechanism under test (auth.py validate_refresh_token):
  SELECT all non-expired refresh_tokens → bcrypt verify_password per row until match.

E2E method (HTTP only, no direct DB required):
  Repeated POST /auth/login accumulates one refresh_tokens row per login; the cookie
  matches the latest row. With rows returned in insertion order, refresh performs
  N bcrypt checks for N accumulated sessions.

Run standalone: python3 scripts/diag/auth_refresh_perf.py
Run pytest:     PYTHONPATH=. pytest tests/e2e/test_auth_refresh_scaling.py -m e2e -v
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from tests.e2e.helpers import admin_credentials, base_url, load_e2e_env

REFRESH_COOKIE = "agent_refresh"
BUG_LOCATION = "apps/backend/infrastructure/auth.py validate_refresh_token (lines ~76–89)"


@dataclass
class RefreshSample:
    login_rounds: int
    refresh_ms: float
    http_status: int


@dataclass
class RefreshScalingReport:
    base: str
    user_email: str
    samples: list[RefreshSample]
    setup_status_ms: float
    refresh_no_cookie_ms: float
    tokens_cleaned: bool
    diagnosis: list[str] = field(default_factory=list)
    bug_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "user_email": self.user_email,
            "samples": [asdict(s) for s in self.samples],
            "setup_status_ms": self.setup_status_ms,
            "refresh_no_cookie_ms": self.refresh_no_cookie_ms,
            "tokens_cleaned": self.tokens_cleaned,
            "diagnosis": self.diagnosis,
            "bug_confirmed": self.bug_confirmed,
            "bug_location": BUG_LOCATION,
        }


def _elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


SLOW_REFRESH_MS = float(os.environ.get("AGENT_E2E_SLOW_REFRESH_MS", "2000"))


def cleanup_refresh_tokens(user_email: str) -> bool:
    """Delete refresh_tokens for test user (docker psql or AGENT_E2E_DATABASE_URL)."""
    db_url = (os.environ.get("AGENT_E2E_DATABASE_URL") or "").strip()
    if db_url:
        os.environ["DATABASE_URL"] = db_url
        from apps.backend.infrastructure.db import db

        db.init_pool()
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM refresh_tokens
                    WHERE user_id = (SELECT id FROM users WHERE email = %s LIMIT 1)
                    """,
                    (user_email.strip().lower(),),
                )
                conn.commit()
        return True

    import shutil

    if not shutil.which("docker"):
        return False
    container = (os.environ.get("AGENT_E2E_POSTGRES_CONTAINER") or "agent-layer-postgres").strip()
    email = user_email.strip().lower()
    proc = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "agent",
            "-d",
            "agent",
            "-v",
            f"user_email={email}",
            "-c",
            "DELETE FROM refresh_tokens WHERE user_id = "
            "(SELECT id FROM users WHERE email = :'user_email' LIMIT 1);",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.returncode == 0


def client_after_logins(email: str, password: str, rounds: int) -> httpx.Client:
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    client = httpx.Client(base_url=base_url(), timeout=120.0)
    for _ in range(rounds):
        resp = client.post("/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        if not client.cookies.get(REFRESH_COOKIE):
            client.close()
            raise RuntimeError("login did not set agent_refresh cookie")
    return client


def measure_refresh(client: httpx.Client) -> tuple[float, int]:
    t0 = time.perf_counter()
    resp = client.post("/auth/refresh", json={})
    return _elapsed_ms(t0), resp.status_code


def measure_setup_status() -> float:
    t0 = time.perf_counter()
    with httpx.Client(base_url=base_url(), timeout=30.0) as client:
        resp = client.get("/auth/setup-status")
        resp.raise_for_status()
    return _elapsed_ms(t0)


def run_scaling_report(*, login_rounds: list[int] | None = None) -> RefreshScalingReport:
    load_e2e_env()
    login_rounds = login_rounds or [1, 21, 41]
    email, password = admin_credentials()
    tokens_cleaned = cleanup_refresh_tokens(email)
    samples: list[RefreshSample] = []

    with httpx.Client(base_url=base_url(), timeout=30.0) as anon:
        t0 = time.perf_counter()
        anon.post("/auth/refresh", json={})
        refresh_no_cookie_ms = _elapsed_ms(t0)

    for rounds in login_rounds:
        cleanup_refresh_tokens(email)
        client = client_after_logins(email, password, rounds)
        try:
            ms, status = measure_refresh(client)
        finally:
            client.close()
        samples.append(RefreshSample(login_rounds=rounds, refresh_ms=ms, http_status=status))

    setup_ms = measure_setup_status()
    cleanup_refresh_tokens(email)

    report = RefreshScalingReport(
        base=base_url(),
        user_email=email,
        samples=samples,
        setup_status_ms=setup_ms,
        refresh_no_cookie_ms=refresh_no_cookie_ms,
        tokens_cleaned=tokens_cleaned,
    )
    report.diagnosis = build_diagnosis(report)
    report.bug_confirmed = is_bug_confirmed(report)
    return report


def is_bug_confirmed(report: RefreshScalingReport) -> bool:
    if not report.samples:
        return False
    slow = [s for s in report.samples if s.http_status == 200 and s.refresh_ms >= SLOW_REFRESH_MS]
    if slow:
        return True
    if len(report.samples) < 2:
        return False
    first = report.samples[0]
    last = report.samples[-1]
    if last.http_status != 200 or first.http_status != 200:
        return False
    if last.login_rounds < 10:
        return False
    return last.refresh_ms >= max(SLOW_REFRESH_MS, first.refresh_ms * 3.0)


def build_diagnosis(report: RefreshScalingReport) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"POST /auth/refresh without cookie: {report.refresh_no_cookie_ms}ms "
        "(must stay fast; not the spinner bug)."
    )
    lines.append(
        f"GET /auth/setup-status after test: {report.setup_status_ms}ms "
        "(must stay fast; LLM decoupling is separate from refresh bug)."
    )

    if not report.tokens_cleaned:
        lines.append(
            "WARN: could not DELETE refresh_tokens before test (set AGENT_E2E_DATABASE_URL or run "
            "with docker access to agent-layer-postgres). Absolute refresh_ms may include old rows."
        )

    if len(report.samples) >= 1:
        s0 = report.samples[0]
        lines.append(
            f"POST /auth/refresh with cookie after {s0.login_rounds} login(s) "
            f"(clean DB): {s0.refresh_ms}ms http={s0.http_status}."
        )
    if len(report.samples) >= 2:
        last = report.samples[-1]
        lines.append(
            f"After {last.login_rounds} login(s): {last.refresh_ms}ms "
            f"(indexed sha256 lookup — should stay flat)."
        )

    if is_bug_confirmed(report):
        lines.append(
            f"BUG CONFIRMED at {BUG_LOCATION}: POST /auth/refresh >= {SLOW_REFRESH_MS}ms with "
            f"refresh_tokens accumulated. AuthContext awaits refresh before loading=false "
            f"(login 'Wird geladen…'). NOT setup-status. NOT projects dashboard."
        )
    else:
        lines.append(
            f"No refresh >= {SLOW_REFRESH_MS}ms in this run (bug may be fixed or cleanup failed)."
        )
    return lines


def format_failure(report: RefreshScalingReport) -> str:
    lines = [
        "AUTH REFRESH SCALING E2E",
        f"location: {BUG_LOCATION}",
        f"base: {report.base}",
        f"user: {report.user_email}",
        "",
        "login_rounds  refresh_ms  http",
    ]
    for s in report.samples:
        lines.append(f"{s.login_rounds:>12}  {s.refresh_ms:>10.2f}  {s.http_status}")
    lines.append("")
    lines.extend(report.diagnosis)
    return "\n".join(lines)
