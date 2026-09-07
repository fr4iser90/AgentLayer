#!/usr/bin/env python3
"""Drive one real chat turn that delegates into the coding vertical.

``/v1/chat/completions`` forces ``agent_id`` to a chat-surface agent, so specialists are
only reachable when ``general`` delegates. The prompt therefore asks for a build task and
the resulting sub-run is what exercises the coding allowlist.

Check the effect in the backend log:

    docker compose logs agent-layer | rg tools_pipeline

Expected for the sub-run: ``agent=coding allowlist=49->built=49(full)->rank=49->llm=49``,
i.e. every declared tool survives ranking and ships a full schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.e2e.support.helpers import admin_credentials, base_url, load_e2e_env  # noqa: E402

# Pass a model that the LLM host currently has loaded; the provider default may differ.
MODEL = "Qwen3-Coder-30B-A3B-Instruct-UD-Q5_K_XL"
PROMPT = (
    "Delegate to the coding agent (build mode): create a file notes.txt in the workspace "
    "root containing the single line hello, then confirm it exists."
)


def main() -> int:
    load_e2e_env()
    model = sys.argv[1] if len(sys.argv) > 1 else MODEL
    with httpx.Client(base_url=base_url(), timeout=600.0) as c:
        email, password = admin_credentials()
        token = c.post("/auth/login", json={"email": email, "password": password}).json()[
            "access_token"
        ]

        print(f"model  : {model}")
        print(f"prompt : {PROMPT}\n")
        r = c.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT}],
                "stream": False,
            },
        )
        print(f"HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:1500])
            return 1

        data = r.json()
        print(f"usage  : {data.get('usage')}")
        content = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        print(f"\nreply ({len(content)} chars):\n{content[:1500] or '(empty)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
