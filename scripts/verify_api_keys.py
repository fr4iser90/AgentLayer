#!/usr/bin/env python3
"""Live check for per-user API keys (ADR 0008).

Asserts that a minted key authenticates HTTP and the chat WebSocket, that the secret is
stored hashed, that key management rejects the key itself, and that revocation takes effect.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import websockets

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.e2e.support.helpers import admin_credentials, base_url, load_e2e_env  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


def _db_row_for(name: str) -> str:
    out = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "postgres",
            "psql", "-U", "agent", "-d", "agent", "-t", "-A",
            "-c", f"SELECT key_hash FROM api_keys WHERE name = '{name}' LIMIT 1;",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return (out.stdout or "").strip()


async def _ws_accepts(token: str) -> bool:
    url = base_url().replace("http://", "ws://").replace("https://", "wss://")
    try:
        async with websockets.connect(f"{url}/ws/v1/chat?token={token}", open_timeout=20) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            return reply.get("type") == "pong"
    except Exception:
        return False


def main() -> int:
    load_e2e_env()
    name = "verify-api-keys-probe"
    with httpx.Client(base_url=base_url(), timeout=60.0) as c:
        email, password = admin_credentials()
        jwt = c.post("/auth/login", json={"email": email, "password": password}).json()[
            "access_token"
        ]
        jwt_h = {"Authorization": f"Bearer {jwt}"}

        # Clean up a previous probe so reruns stay idempotent.
        for row in (c.get("/v1/user/api-keys", headers=jwt_h).json().get("api_keys") or []):
            if row.get("name") == name:
                c.delete(f"/v1/user/api-keys/{row['id']}", headers=jwt_h)

        print("mint")
        r = c.post("/v1/user/api-keys", headers=jwt_h, json={"name": name})
        check("POST /v1/user/api-keys returns 200", r.status_code == 200, r.text[:120])
        if r.status_code != 200:
            return 1
        body = r.json()
        key = body.get("api_key") or ""
        key_id = (body.get("key") or {}).get("id")
        check("secret is returned once and prefixed", key.startswith("al_"), key[:6] + "…")

        print("storage")
        stored = _db_row_for(name)
        check("database stores a digest, not the secret", stored != key and len(stored) == 64,
              f"len={len(stored)}")

        print("authentication")
        r = c.get("/v1/agents", headers={"Authorization": f"Bearer {key}"})
        check("key authenticates HTTP", r.status_code == 200, f"HTTP {r.status_code}")
        check("key authenticates the chat WebSocket", asyncio.run(_ws_accepts(key)))
        check("a bogus key is rejected on the WebSocket", not asyncio.run(_ws_accepts("al_nope")))

        print("management is session-only")
        r = c.post("/v1/user/api-keys", headers={"Authorization": f"Bearer {key}"},
                   json={"name": "escalation"})
        check("minting with a key is refused", r.status_code == 403, f"HTTP {r.status_code}")
        r = c.delete(f"/v1/user/api-keys/{key_id}", headers={"Authorization": f"Bearer {key}"})
        check("revoking with a key is refused", r.status_code == 403, f"HTTP {r.status_code}")

        print("listing")
        rows = c.get("/v1/user/api-keys", headers=jwt_h).json().get("api_keys") or []
        mine = [x for x in rows if x.get("id") == key_id]
        check("key appears in the list", len(mine) == 1)
        check("list never exposes the secret", all("api_key" not in x and "key_hash" not in x
                                                   for x in rows))
        check("last_used_at was recorded", bool(mine and mine[0].get("last_used_at")),
              str(mine[0].get("last_used_at"))[:19] if mine else "")

        print("revocation")
        r = c.delete(f"/v1/user/api-keys/{key_id}", headers=jwt_h)
        check("DELETE with the session succeeds", r.status_code == 200, f"HTTP {r.status_code}")
        r = c.get("/v1/agents", headers={"Authorization": f"Bearer {key}"})
        check("revoked key no longer authenticates", r.status_code == 401, f"HTTP {r.status_code}")
        check("revoked key rejected on the WebSocket", not asyncio.run(_ws_accepts(key)))

        print("expiry")
        r = c.post("/v1/user/api-keys", headers=jwt_h,
                   json={"name": name, "expires_in_days": 1})
        check("expires_in_days is accepted", r.status_code == 200, r.text[:120])
        if r.status_code == 200:
            kid = (r.json().get("key") or {}).get("id")
            exp = (r.json().get("key") or {}).get("expires_at")
            check("expiry is persisted", bool(exp), str(exp)[:19])
            c.delete(f"/v1/user/api-keys/{kid}", headers=jwt_h)
        r = c.post("/v1/user/api-keys", headers=jwt_h,
                   json={"name": name, "expires_in_days": 100000})
        check("absurd TTL is rejected", r.status_code == 422, f"HTTP {r.status_code}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
