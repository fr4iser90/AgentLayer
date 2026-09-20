#!/usr/bin/env python3
"""Bootstrap a fresh AgentLayer instance to a validated, testable state.

Why this exists: on a wiped database the path from "container running" to
"usable app" is not one step, and two of its steps are easy to get wrong.

  * The deployment mode can only be chosen through the setup endpoint while
    no admin exists. `apply_setup_deployment_mode` raises 409 afterwards
    (`apps/backend/domain/setup/instance.py`), so a box that bootstrapped
    its admin from `AGENT_INITIAL_ADMIN_*` has already missed that window
    and must set the mode as an admin instead.
  * `needs_provider_wizard` stays true until a DB endpoint carries a
    `model_default`. While it is true, a non-admin is redirected to
    /app/setup and has no way into the application — every non-admin UI
    check silently tests a redirect page instead of the real screen.

The model default is validated against the live provider catalog before it
is written. A stale `LLM_PROVIDER_1_MODEL_DEFAULT` in .env (a GGUF
filename the provider no longer serves under that name) would otherwise be
written into the DB and produce a chat that fails at the first round,
which reads as a broken app rather than a stale config line.

Stdlib-only, so it runs on the host without a venv — same convention as
scripts/e2e_auth_smoke.py.

Usage:
    python3 scripts/bootstrap_instance.py [--deployment-mode multi_tenant]
                                        [--model chat] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
DEPLOYMENT_MODES = ("single_user", "agent_system", "multi_tenant")


def load_env() -> None:
    """Populate os.environ from .env without overriding what is already set."""
    for name in (".env", ".env.e2e"):
        path = REPO / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def base_url() -> str:
    # AGENT_E2E_BASE_URL wins, matching every other script in this set.
    explicit = (os.environ.get("AGENT_E2E_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = (os.environ.get("AGENT_HTTP_PORT") or "8088").strip()
    return f"http://127.0.0.1:{port}"


def call(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    url = f"{base_url()}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _maybe_json(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, _maybe_json(raw)
    except urllib.error.URLError as exc:
        return 0, {"error": f"{type(exc.reason).__name__}: {exc.reason}"}


def _maybe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw[:400]


class Boot:
    def __init__(self) -> None:
        self.steps: list[dict[str, str]] = []
        self.failed = False

    def note(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append({"step": name, "status": status, "detail": detail})
        mark = {"ok": "PASS", "skip": "SKIP", "fail": "FAIL"}[status]
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        if status == "fail":
            self.failed = True

    def login(self, email: str, password: str) -> str | None:
        status, body = call("POST", "/auth/login", body={"email": email, "password": password})
        if status != 200 or not isinstance(body, dict):
            self.note(f"login {email}", "fail", f"HTTP {status}: {body}")
            return None
        self.note(f"login {email}", "ok", f"role={body.get('user', {}).get('role', '?')}")
        return body.get("access_token")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a fresh AgentLayer instance.")
    parser.add_argument("--deployment-mode", choices=DEPLOYMENT_MODES, default=None)
    parser.add_argument("--model", default=None, help="chat model_default to write to the DB")
    parser.add_argument("--setup-token", default=None)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable summary")
    args = parser.parse_args()

    load_env()
    boot = Boot()

    status, setup = call("GET", "/auth/setup-status")
    if status != 200 or not isinstance(setup, dict):
        print(f"cannot read /auth/setup-status: HTTP {status} {setup}", file=sys.stderr)
        return 2
    print(f"base: {base_url()}")
    print(
        "setup-status: "
        f"needs_admin={setup.get('needs_admin')} "
        f"needs_provider_wizard={setup.get('needs_provider_wizard')} "
        f"deployment_mode={setup.get('deployment_mode')}"
    )

    admin_email = os.environ.get("AGENT_INITIAL_ADMIN_EMAIL") or os.environ.get("AGENT_E2E_EMAIL") or ""
    admin_password = os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD") or os.environ.get("AGENT_E2E_PASSWORD") or ""

    # ── First-start path: mode must be chosen before any admin exists ──
    if setup.get("needs_admin"):
        token = args.setup_token or os.environ.get("AGENT_SETUP_TOKEN") or ""
        if not token:
            boot.note(
                "first-start setup token",
                "fail",
                "no admin yet and no AGENT_SETUP_TOKEN — cannot create one",
            )
        else:
            if args.deployment_mode:
                s, b = call(
                    "POST",
                    "/auth/setup/deployment-mode",
                    body={"deployment_mode": args.deployment_mode, "setup_token": token},
                )
                boot.note(
                    "deployment mode via setup endpoint",
                    "ok" if s == 200 else "fail",
                    f"HTTP {s}: {b}",
                )
            s, b = call(
                "POST",
                "/auth/setup",
                body={
                    "email": admin_email,
                    "password": admin_password,
                    "password_confirm": admin_password,
                    "setup_token": token,
                },
            )
            boot.note("create first admin", "ok" if s in (200, 201) else "fail", f"HTTP {s}")
        # Re-read after the admin exists.
        _, setup = call("GET", "/auth/setup-status")

    # ── Admin session ──
    token = boot.login(admin_email, admin_password) if admin_email else None
    if not token:
        print("no admin session; cannot continue", file=sys.stderr)
        return 1

    # ── Deployment mode, post-setup path ──
    if args.deployment_mode:
        current = (setup or {}).get("deployment_mode")
        if current == args.deployment_mode:
            boot.note("deployment mode", "skip", f"already {args.deployment_mode}")
        else:
            s, b = call(
                "PATCH",
                "/v1/admin/operator-settings",
                body={"deployment_mode": args.deployment_mode},
                token=token,
            )
            applied = isinstance(b, dict) and b.get("deployment_mode") == args.deployment_mode
            boot.note(
                f"deployment mode -> {args.deployment_mode}",
                "ok" if s == 200 and applied else "fail",
                f"HTTP {s}, read-back={b.get('deployment_mode') if isinstance(b, dict) else b}",
            )

    # ── Provider wizard ──
    _, setup = call("GET", "/auth/setup-status")
    if isinstance(setup, dict) and not setup.get("needs_provider_wizard"):
        boot.note("provider wizard", "skip", "already satisfied")
    else:
        provider_base = (os.environ.get("LLM_PROVIDER_1_BASE_URL") or "").strip()
        provider_key = (os.environ.get("LLM_PROVIDER_1_API_KEY") or "").strip()
        configured = (os.environ.get("LLM_PROVIDER_1_MODEL_DEFAULT") or "").strip()

        if not provider_base:
            boot.note("provider wizard", "fail", "LLM_PROVIDER_1_BASE_URL unset")
        else:
            # Validate the requested model against the live catalog rather
            # than trusting .env.
            s, probe = call(
                "POST",
                "/auth/setup/llm",
                body={
                    "base_url": provider_base,
                    "api_key": provider_key or None,
                    "model_default": None,
                    "label": os.environ.get("LLM_PROVIDER_1_LABEL") or "LLM",
                    "test_only": True,
                },
                token=token,
            )
            live = probe.get("models", []) if isinstance(probe, dict) else []
            if s != 200:
                boot.note("provider probe", "fail", f"HTTP {s}: {probe}")
            else:
                boot.note("provider probe", "ok", f"{len(live)} modelle live")
                want = args.model or configured
                if want and want not in live:
                    boot.note(
                        f"requested model '{want}'",
                        "fail",
                        f"not served by provider. live={live}",
                    )
                    print(
                        f"\n  .env LLM_PROVIDER_1_MODEL_DEFAULT='{configured}' is stale.\n"
                        f"  Provider serves: {live}\n"
                        f"  Pass --model <one of the above> to proceed.\n",
                        file=sys.stderr,
                    )
                else:
                    s2, b2 = call(
                        "POST",
                        "/auth/setup/llm",
                        body={
                            "base_url": provider_base,
                            "api_key": provider_key or None,
                            "model_default": want,
                            "label": os.environ.get("LLM_PROVIDER_1_LABEL") or "LLM",
                            "test_only": False,
                        },
                        token=token,
                    )
                    boot.note(
                        f"write model_default='{want}' to DB",
                        "ok" if s2 == 200 else "fail",
                        f"HTTP {s2}",
                    )

    # ── Final verification ──
    _, final = call("GET", "/auth/setup-status")
    if isinstance(final, dict):
        wizard = final.get("needs_provider_wizard")
        boot.note(
            "needs_provider_wizard == false",
            "ok" if wizard is False else "fail",
            f"ist {wizard}",
        )
        print(
            "final: "
            f"needs_admin={final.get('needs_admin')} "
            f"needs_provider_wizard={wizard} "
            f"deployment_mode={final.get('deployment_mode')}"
        )

    if args.json:
        print(json.dumps({"steps": boot.steps, "failed": boot.failed}, indent=2))

    return 1 if boot.failed else 0


if __name__ == "__main__":
    sys.exit(main())
